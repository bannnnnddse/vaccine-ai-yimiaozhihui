from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from xml.etree import ElementTree

import pymupdf

from app.rag.text import clean_text

ParseStatus = Literal[
    "parsed", "partial", "ocr_parsed", "no_text", "failed", "unsupported"
]
ReviewStatus = Literal[
    "existing_approved", "human_approved", "auto_classified", "needs_review"
]

_SUPPORTED_SUFFIXES = {".pdf", ".md", ".docx"}
_DATE_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?")
_YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_MD_HEADER_PATTERN = re.compile(r"^>\s*([^：:]+)[：:]\s*(.*?)\s*$")
_OFFICIAL_CUES = (
    "国家疾控", "中国疾控", "疾病预防控制中心", "国家卫生健康", "卫健委",
    "中华人民共和国", "国家免疫规划", "接种工作规范", "技术方案", "who", "世界卫生组织",
)
_ACADEMIC_TOPICS = {
    "病原体、疾病负担与疫苗机理",
    "权威指南、科普数字化与可视化",
    "特殊人群接种策略·",
    "疫苗 有效性与免疫持久性",
    "疫苗安全性",
    "疫苗技术路线与产品类型",
    "疫苗接种政策方案与卫生经济学",
    "疫苗犹豫健康科普传播",
}


@dataclass(slots=True)
class CorpusDocument:
    doc_id: str
    title: str
    filename: str
    relative_path: str
    content_hash: str
    source_type: str
    issuer: str
    authority_level: int
    evidence_level: str
    publication_date: str | None
    publication_year: int | None
    effective_date: str | None
    version: str
    language: str
    topic: str
    review_status: ReviewStatus
    is_superseded: bool
    duplicate_of: str | None
    parse_status: ParseStatus
    page_count: int | None
    notes: list[str] = field(default_factory=list)
    text_char_count: int = 0
    text_page_count: int | None = None
    low_text_page_count: int | None = None
    metadata_confidence: str = "low"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def stable_document_id(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/").strip().casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"doc_{digest}"


def scan_corpus(source_dir: Path) -> tuple[list[CorpusDocument], dict[str, object]]:
    root = source_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"RAG source directory does not exist: {source_dir}")
    tracked = _tracked_corpus_paths(root)
    documents: list[CorpusDocument] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=_path_key):
        if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        relative_path = path.relative_to(root).as_posix()
        is_existing = relative_path.casefold() in tracked
        documents.append(_scan_document(path, root, is_existing=is_existing))

    canonical_by_hash: dict[str, CorpusDocument] = {}
    for document in sorted(
        documents,
        key=lambda item: (item.review_status != "existing_approved", item.relative_path.casefold()),
    ):
        canonical = canonical_by_hash.get(document.content_hash)
        if canonical is None:
            canonical_by_hash[document.content_hash] = document
        else:
            document.duplicate_of = canonical.doc_id
            document.notes.append(f"exact duplicate of {canonical.relative_path}")

    _apply_overrides(documents, root / "corpus_overrides.json")

    summary = _summarize(documents)
    return documents, summary


def write_corpus_manifest(
    source_dir: Path,
    manifest_path: Path,
    summary_path: Path,
) -> tuple[list[CorpusDocument], dict[str, object]]:
    documents, summary = scan_corpus(source_dir)
    _write_atomic(
        manifest_path,
        "".join(
            json.dumps(document.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
            for document in documents
        ),
    )
    _write_atomic(summary_path, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return documents, summary


def load_corpus_manifest(path: Path) -> list[CorpusDocument]:
    documents: list[CorpusDocument] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            documents.append(CorpusDocument(**json.loads(line)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid corpus manifest line {line_number}") from exc
    return documents


def _scan_document(path: Path, root: Path, *, is_existing: bool) -> CorpusDocument:
    relative_path = path.relative_to(root).as_posix()
    content = path.read_bytes()
    content_hash = hashlib.sha256(content).hexdigest()
    topic = relative_path.split("/", 1)[0] if "/" in relative_path else "未分类"
    notes: list[str] = []
    metadata: dict[str, str] = {}
    preview = ""
    page_count: int | None = None
    text_pages: int | None = None
    low_text_pages: int | None = None
    parse_status: ParseStatus = "unsupported"

    try:
        if path.suffix.lower() == ".pdf":
            (
                metadata,
                preview,
                page_count,
                text_pages,
                low_text_pages,
                text_char_count,
                parse_status,
            ) = _inspect_pdf(path)
            if low_text_pages:
                notes.append(f"{low_text_pages} PDF pages have fewer than 50 text characters")
        elif path.suffix.lower() == ".md":
            raw_text = path.read_text(encoding="utf-8")
            metadata = _markdown_metadata(raw_text)
            preview = clean_text(raw_text)[:12_000]
            text_char_count = len(re.sub(r"\s+", "", preview))
            parse_status = "parsed" if text_char_count else "no_text"
        elif path.suffix.lower() == ".docx":
            preview, text_char_count = _docx_text(path)
            parse_status = "parsed" if text_char_count >= 50 else "no_text"
            if parse_status == "no_text":
                notes.append("DOCX contains no substantive text; likely a download placeholder")
        else:
            text_char_count = 0
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, KeyError) as exc:
        parse_status = "failed"
        text_char_count = 0
        notes.append(f"parse failed: {type(exc).__name__}")

    title = _select_title(path, metadata, preview)
    combined = "\n".join((title, path.stem, preview[:8_000]))
    identity_text = "\n".join(
        (
            title,
            path.stem,
            metadata.get("来源机构", ""),
            metadata.get("author", ""),
            metadata.get("Author", ""),
        )
    )
    source_type, issuer, authority, source_confidence = _classify_source(
        path,
        topic,
        metadata,
        identity_text,
    )
    evidence = _classify_evidence(f"{title}\n{path.stem}", source_type)
    publication_date, publication_year = _publication_date(metadata, combined)
    version = _version(title, path.stem, publication_year)
    review_status: ReviewStatus
    if source_type == "curated":
        review_status = "human_approved"
    elif is_existing:
        review_status = "existing_approved"
    elif parse_status in {"parsed", "partial"} and source_confidence != "low":
        review_status = "auto_classified"
        notes.append("source/evidence metadata is automated and has not been human-confirmed")
    else:
        review_status = "needs_review"
    if evidence == "unknown" and not is_existing and source_type != "curated":
        review_status = "needs_review"
        notes.append("evidence level could not be inferred reliably")
    if parse_status in {"no_text", "failed", "unsupported"}:
        review_status = "needs_review"

    language = "zh" if _mostly_cjk(preview or title) else "en"
    return CorpusDocument(
        doc_id=stable_document_id(relative_path),
        title=title,
        filename=path.name,
        relative_path=relative_path,
        content_hash=content_hash,
        source_type=source_type,
        issuer=issuer,
        authority_level=authority,
        evidence_level=evidence,
        publication_date=publication_date,
        publication_year=publication_year,
        effective_date=None,
        version=version,
        language=language,
        topic=topic,
        review_status=review_status,
        is_superseded=False,
        duplicate_of=None,
        parse_status=parse_status,
        page_count=page_count,
        notes=notes,
        text_char_count=text_char_count,
        text_page_count=text_pages,
        low_text_page_count=low_text_pages,
        metadata_confidence=source_confidence,
    )


def _inspect_pdf(
    path: Path,
) -> tuple[dict[str, str], str, int, int, int, int, ParseStatus]:
    with pymupdf.open(path) as document:
        metadata = {
            str(key): str(value).strip()
            for key, value in (document.metadata or {}).items()
            if value
        }
        previews: list[str] = []
        text_pages = 0
        low_text_pages = 0
        text_char_count = 0
        for page_index, page in enumerate(document):
            text = clean_text(page.get_text("text", sort=True))
            count = len(re.sub(r"\s+", "", text))
            text_char_count += count
            if count >= 50:
                text_pages += 1
            else:
                low_text_pages += 1
            if page_index < 3 and text:
                previews.append(text)
        if text_pages == 0:
            status: ParseStatus = "no_text"
        elif low_text_pages:
            status = "partial"
        else:
            status = "parsed"
        return (
            metadata,
            "\n".join(previews)[:12_000],
            document.page_count,
            text_pages,
            low_text_pages,
            text_char_count,
            status,
        )


def _docx_text(path: Path) -> tuple[str, int]:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    values = [value.strip() for value in root.itertext() if value.strip()]
    text = clean_text("\n".join(values))
    return text[:12_000], len(re.sub(r"\s+", "", text))


def _markdown_metadata(raw_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in raw_text.splitlines():
        match = _MD_HEADER_PATTERN.match(line)
        if match:
            metadata[match.group(1).strip()] = match.group(2).strip()
            continue
        if line.strip() in {"", ">", "---"}:
            continue
        break
    return metadata


def _select_title(path: Path, metadata: dict[str, str], preview: str) -> str:
    candidates = (
        metadata.get("原始标题"),
        metadata.get("title"),
        metadata.get("Title"),
    )
    for candidate in candidates:
        if candidate and not _generic_pdf_title(candidate):
            return clean_text(candidate)[:500]
    first_line = next((line.strip() for line in preview.splitlines() if line.strip()), "")
    if 4 <= len(first_line) <= 300 and not re.fullmatch(r"\d+", first_line):
        if len(path.stem) < 8 or path.stem.lower().startswith(("download", "fulltext")):
            return first_line
    return path.stem.strip()[:500]


def _generic_pdf_title(value: str) -> bool:
    normalized = value.strip().casefold()
    return not normalized or normalized in {"untitled", "microsoft word", "document"}


def _classify_source(
    path: Path,
    topic: str,
    metadata: dict[str, str],
    combined: str,
) -> tuple[str, str, int, str]:
    issuer = (
        metadata.get("来源机构")
        or metadata.get("author")
        or metadata.get("Author")
        or "unknown"
    )
    url = metadata.get("原始链接", "")
    host = urlparse(url).netloc.casefold() if url else ""
    normalized = combined.casefold()
    official = any(cue in normalized for cue in _OFFICIAL_CUES) or host.endswith(
        (".gov.cn", "chinacdc.cn", "who.int")
    )
    if path.suffix.lower() == ".docx":
        return "download_placeholder", issuer, 0, "low"
    if path.suffix.lower() == ".md":
        if metadata.get("来源类型") == "curated":
            return "curated", issuer, 3, "high"
        if official:
            return "official_web", issuer, 4, "high"
        return "web", issuer, 1, "medium" if url else "low"
    if topic in _ACADEMIC_TOPICS and path.suffix.lower() == ".pdf" and not official:
        has_bibliography = bool(_DOI_PATTERN.search(combined)) or any(
            marker in normalized for marker in ("abstract", "摘要")
        )
        return "academic_paper", issuer, 2, "medium" if has_bibliography else "low"
    if official:
        if issuer == "unknown":
            issuer = _issuer_from_text(normalized)
        return "official_document", issuer, 4, "medium"
    if topic in _ACADEMIC_TOPICS and path.suffix.lower() == ".pdf":
        has_bibliography = bool(_DOI_PATTERN.search(combined)) or any(
            marker in normalized for marker in ("abstract", "摘要", "references", "参考文献")
        )
        return "academic_paper", issuer, 2, "medium" if has_bibliography else "low"
    return "professional_material", issuer, 1, "low"


def _issuer_from_text(normalized: str) -> str:
    mapping = (
        ("世界卫生组织", "WHO"),
        ("who", "WHO"),
        ("国家疾病预防控制局", "国家疾病预防控制局"),
        ("中国疾病预防控制中心", "中国疾病预防控制中心"),
        ("国家卫生健康委员会", "国家卫生健康委员会"),
    )
    return next((issuer for cue, issuer in mapping if cue in normalized), "unknown")


def _classify_evidence(combined: str, source_type: str) -> str:
    text = combined.casefold()
    rules = (
        (
            ("meta分析", "meta-analysis", "meta analysis", "系统综述", "systematic review"),
            "systematic_review_meta_analysis",
        ),
        (
            ("随机对照", "随机试验", "randomized", "randomised", " rct "),
            "randomized_controlled_trial",
        ),
        (("队列研究", "cohort"), "cohort"),
        (("病例对照", "case-control", "case control"), "case_control"),
        (("横断面", "cross-sectional", "cross sectional"), "cross_sectional"),
        (("专家共识", "expert consensus", "consensus"), "expert_consensus"),
        (("指南", "guideline", "工作规范", "技术方案"), "guideline"),
        (("叙述性综述", "narrative review"), "narrative_review"),
        (("综述", "review"), "review_unspecified"),
        (("科普", "知识问答", "science communication"), "science_communication"),
    )
    for cues, evidence in rules:
        if any(cue in text for cue in cues):
            return evidence
    if source_type == "official_document":
        return "official_policy_or_reference"
    return "unknown"


def _publication_date(metadata: dict[str, str], combined: str) -> tuple[str | None, int | None]:
    # PDF CreationDate is commonly the download, translation, or conversion time rather
    # than the source publication date, so it is intentionally excluded.
    for key in ("发布日期", "publication_date"):
        value = metadata.get(key)
        if not value:
            continue
        parsed = _parse_date(value)
        if parsed:
            return parsed, int(parsed[:4])
    match = _DATE_PATTERN.search(combined[:4_000])
    if match:
        year, month, day = (int(item) for item in match.groups())
        try:
            value = datetime(year, month, day).date().isoformat()
            return value, year
        except ValueError:
            pass
    years = [int(value) for value in _YEAR_PATTERN.findall(combined[:4_000])]
    plausible = [year for year in years if 1900 <= year <= datetime.now().year]
    return None, plausible[0] if plausible else None


def _parse_date(value: str) -> str | None:
    pdf_match = re.search(r"D:((?:19|20)\d{2})(\d{2})(\d{2})", value)
    match = pdf_match or _DATE_PATTERN.search(value)
    if not match:
        return None
    year, month, day = (int(item) for item in match.groups())
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def _version(title: str, stem: str, publication_year: int | None) -> str:
    text = f"{title} {stem}"
    pattern = r"((?:19|20)\d{2}\s*年?版|第[一二三四五六七八九十\d]+版|v\d+(?:\.\d+)*)"
    match = re.search(pattern, text, re.I)
    if match:
        return re.sub(r"\s+", "", match.group(1))
    return "unknown"


def _mostly_cjk(value: str) -> bool:
    letters = re.findall(r"[A-Za-z\u3400-\u9fff]", value[:4_000])
    if not letters:
        return True
    cjk = sum("\u3400" <= char <= "\u9fff" for char in letters)
    return cjk / len(letters) >= 0.35


def _tracked_corpus_paths(root: Path) -> set[str]:
    repository = root.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "ls-files", "RAG/**"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {
        line.removeprefix("RAG/").replace("\\", "/").casefold()
        for line in result.stdout.splitlines()
        if line.strip()
    }


def _summarize(documents: list[CorpusDocument]) -> dict[str, object]:
    def counts(attribute: str) -> dict[str, int]:
        values: dict[str, int] = {}
        for document in documents:
            key = str(getattr(document, attribute))
            values[key] = values.get(key, 0) + 1
        return dict(sorted(values.items()))

    years: dict[str, int] = {}
    for document in documents:
        key = str(document.publication_year) if document.publication_year else "unknown"
        years[key] = years.get(key, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(documents),
        "unique_content_count": len({item.content_hash for item in documents}),
        "duplicate_file_count": sum(item.duplicate_of is not None for item in documents),
        "parse_status": counts("parse_status"),
        "source_types": counts("source_type"),
        "authority_levels": counts("authority_level"),
        "evidence_levels": counts("evidence_level"),
        "review_status": counts("review_status"),
        "publication_years": dict(sorted(years.items())),
        "missing_metadata": {
            "issuer_unknown": sum(item.issuer == "unknown" for item in documents),
            "publication_date_unknown": sum(item.publication_date is None for item in documents),
            "publication_year_unknown": sum(item.publication_year is None for item in documents),
            "version_unknown": sum(item.version == "unknown" for item in documents),
            "evidence_unknown": sum(item.evidence_level == "unknown" for item in documents),
        },
        "page_count": sum(item.page_count or 0 for item in documents),
        "text_page_count": sum(item.text_page_count or 0 for item in documents),
        "low_text_page_count": sum(item.low_text_page_count or 0 for item in documents),
        "parse_failures": [
            item.relative_path
            for item in documents
            if item.parse_status in {"failed", "no_text", "unsupported"}
        ],
        "suspected_superseded": [
            item.relative_path for item in documents if item.is_superseded
        ],
        "duplicate_files": [
            {"relative_path": item.relative_path, "duplicate_of": item.duplicate_of}
            for item in documents
            if item.duplicate_of
        ],
    }


def _apply_overrides(documents: list[CorpusDocument], path: Path) -> None:
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid corpus overrides") from exc
    overrides = payload.get("overrides")
    if not isinstance(overrides, dict):
        raise ValueError("corpus overrides must contain an overrides object")
    by_path = {document.relative_path: document for document in documents}
    allowed = {
        "source_type",
        "issuer",
        "authority_level",
        "evidence_level",
        "publication_date",
        "publication_year",
        "effective_date",
        "version",
        "review_status",
        "is_superseded",
        "metadata_confidence",
        "parse_status",
        "text_char_count",
        "text_page_count",
        "low_text_page_count",
    }
    for relative_path, values in overrides.items():
        document = by_path.get(relative_path)
        if document is None or not isinstance(values, dict):
            raise ValueError(f"corpus override target is invalid: {relative_path}")
        unknown = set(values) - allowed - {"notes_append"}
        if unknown:
            raise ValueError(f"unsupported corpus override fields: {sorted(unknown)}")
        for field_name in allowed:
            if field_name in values:
                setattr(document, field_name, values[field_name])
        notes = values.get("notes_append", [])
        if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
            raise ValueError("corpus override notes_append must be a string list")
        document.notes.extend(notes)


def _path_key(path: Path) -> str:
    return path.as_posix().casefold()


def _write_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
