from __future__ import annotations

import re
from pathlib import Path

from app.rag.corpus import CorpusDocument
from app.rag.markdown_loader import _split_metadata
from app.rag.models import IndexReport, PageDocument
from app.rag.text import clean_text

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def load_structured_markdown(
    source_dir: Path,
    documents: list[CorpusDocument],
) -> tuple[list[PageDocument], IndexReport]:
    output: list[PageDocument] = []
    report = IndexReport()
    for document in documents:
        if not document.filename.lower().endswith(".md") or document.duplicate_of:
            continue
        report.markdown_files_seen += 1
        path = source_dir / Path(document.relative_path)
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            report.warnings.append(
                f"{document.relative_path} Markdown 读取失败：{type(exc).__name__}"
            )
            continue
        metadata, body = _split_metadata(raw_text)
        source_url = metadata.get("原始链接")
        if not source_url:
            report.warnings.append(f"{document.relative_path} 缺少可追溯的原始链接，已跳过")
            continue
        source_type = "curated" if metadata.get("来源类型") == "curated" else "web"
        sections = _markdown_sections(body, document.title)
        for block_index, (section_path, text) in enumerate(sections):
            cleaned = clean_text(text)
            if not cleaned:
                continue
            output.append(
                PageDocument(
                    file_name=document.filename,
                    relative_path=document.relative_path,
                    page=None,
                    text=cleaned,
                    source_hash=document.content_hash,
                    source_type=source_type,
                    corpus_source_type=document.source_type,
                    source_title=document.title,
                    source_url=source_url,
                    section=" > ".join(section_path) or document.title,
                    doc_id=document.doc_id,
                    title=document.title,
                    section_path=section_path,
                    authority_level=document.authority_level,
                    evidence_level=document.evidence_level,
                    publication_date=document.publication_date,
                    publication_year=document.publication_year,
                    effective_date=document.effective_date,
                    version=document.version,
                    is_superseded=document.is_superseded,
                    block_index=block_index,
                )
            )
            report.markdown_sections_indexed += 1
        report.unique_markdown_files += 1
    return output, report


def _markdown_sections(body: str, fallback_title: str) -> list[tuple[tuple[str, ...], str]]:
    output: list[tuple[tuple[str, ...], str]] = []
    stack: list[str] = []
    current_path = (fallback_title,)
    current_lines: list[str] = []
    for line in body.splitlines():
        match = _HEADING_PATTERN.match(line)
        if not match:
            current_lines.append(line)
            continue
        if current_lines:
            output.append((current_path, "\n".join(current_lines)))
        level = len(match.group(1))
        stack[:] = stack[: level - 1]
        stack.append(match.group(2).strip())
        current_path = tuple(stack)
        current_lines = []
    if current_lines:
        output.append((current_path, "\n".join(current_lines)))
    return output
