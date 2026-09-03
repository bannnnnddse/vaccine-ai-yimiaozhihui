import hashlib
import re
from pathlib import Path

from app.rag.models import IndexReport, PageDocument
from app.rag.text import clean_text

_HEADER_PATTERN = re.compile(r"^>\s*([^：:]+)[：:]\s*(.*?)\s*$")
_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*$")


def load_markdown_documents(source_dir: Path) -> tuple[list[PageDocument], IndexReport]:
    """Load traceable web-source Markdown files as section-level documents."""
    report = IndexReport()
    documents: list[PageDocument] = []
    seen_hashes: set[str] = set()

    for path in sorted(source_dir.rglob("*.md")):
        report.markdown_files_seen += 1
        raw_text = path.read_text(encoding="utf-8")
        source_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        relative_path = path.relative_to(source_dir).as_posix()
        if source_hash in seen_hashes:
            report.duplicate_markdown_files.append(relative_path)
            continue
        seen_hashes.add(source_hash)
        report.unique_markdown_files += 1

        metadata, body = _split_metadata(raw_text)
        source_url = metadata.get("原始链接")
        if not source_url:
            report.warnings.append(f"{relative_path} 缺少可追溯的原始链接，已跳过")
            continue
        source_title = metadata.get("原始标题") or path.stem
        source_type = "curated" if metadata.get("来源类型") == "curated" else "web"
        for section, section_text in _split_sections(body, source_title):
            text = clean_text(section_text)
            if not text:
                continue
            documents.append(PageDocument(
                file_name=path.name,
                relative_path=relative_path,
                page=None,
                text=text,
                source_hash=source_hash,
                source_type=source_type,
                source_title=source_title,
                source_url=source_url,
                section=section,
            ))
            report.markdown_sections_indexed += 1
    return documents, report


def _split_metadata(raw_text: str) -> tuple[dict[str, str], str]:
    metadata: dict[str, str] = {}
    lines = raw_text.splitlines()
    body_start = 0
    for index, line in enumerate(lines):
        match = _HEADER_PATTERN.match(line)
        if match:
            metadata[match.group(1).strip()] = match.group(2).strip()
            body_start = index + 1
            continue
        if line.strip() in {"", ">", "---"}:
            body_start = index + 1
            continue
        break
    return metadata, "\n".join(lines[body_start:])


def _split_sections(body: str, fallback_section: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = fallback_section
    current_lines: list[str] = []
    found_heading = False
    for line in body.splitlines():
        match = _HEADING_PATTERN.match(line)
        if match:
            if found_heading or current_lines:
                sections.append((current_title, "\n".join(current_lines)))
            current_title = match.group(1).strip()
            current_lines = []
            found_heading = True
            continue
        current_lines.append(line)
    if found_heading or current_lines:
        sections.append((current_title, "\n".join(current_lines)))
    return sections
