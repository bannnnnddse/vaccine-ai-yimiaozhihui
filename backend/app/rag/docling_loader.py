from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.rag.corpus import CorpusDocument
from app.rag.models import IndexReport, PageDocument
from app.rag.text import clean_text

_SKIP_TEXT_LABELS = {"page_header", "page_footer"}
_SKIP_TABLE_LABELS = {"document_index"}


def load_docling_documents(
    documents: list[CorpusDocument],
    artifact_dir: Path,
) -> tuple[list[PageDocument], IndexReport]:
    """Load structure-aware PDF blocks from cached Docling JSON exports."""
    pages: list[PageDocument] = []
    report = IndexReport()
    for document in documents:
        if not document.filename.lower().endswith(".pdf") or document.duplicate_of:
            continue
        report.docling_files_seen += 1
        artifact = artifact_dir / f"{document.doc_id}.json"
        if not artifact.is_file():
            report.warnings.append(
                f"{document.relative_path} 缺少 Docling JSON，未进入结构化索引"
            )
            continue
        try:
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            loaded = _from_docling_payload(payload, document)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            report.warnings.append(
                f"{document.relative_path} Docling JSON 无法解析：{type(exc).__name__}"
            )
            continue
        if not loaded:
            report.warnings.append(f"{document.relative_path} Docling 未生成有效正文块")
            continue
        pages.extend(loaded)
        report.docling_files_loaded += 1
    return pages, report


def _from_docling_payload(
    payload: dict[str, Any],
    document: CorpusDocument,
) -> list[PageDocument]:
    section_stack: list[str] = []
    output: list[PageDocument] = []
    pending_text: list[str] = []
    pending_page: int | None = None
    pending_section: tuple[str, ...] = ()

    def flush() -> None:
        nonlocal pending_text, pending_page, pending_section
        text = clean_text("\n\n".join(pending_text))
        if text:
            output.append(
                _page_document(
                    document,
                    page=pending_page,
                    text=text,
                    section_path=pending_section,
                )
            )
        pending_text = []

    for item_type, item in _iter_body_items(payload):
        if item_type == "text":
            label = str(item.get("label", "text"))
            if label in _SKIP_TEXT_LABELS:
                continue
            text = clean_text(str(item.get("text", "")))
            if not text:
                continue
            page = _page_number(item)
            if label == "section_header":
                flush()
                level = max(1, int(item.get("level") or 1))
                section_stack[:] = section_stack[: level - 1]
                section_stack.append(text[:300])
                pending_page = page
                pending_section = tuple(section_stack)
                continue
            section_path = tuple(section_stack)
            if pending_text and (page != pending_page or section_path != pending_section):
                flush()
            pending_page = page
            pending_section = section_path
            pending_text.append(text)
            continue

        if item_type == "table":
            if str(item.get("label", "table")) in _SKIP_TABLE_LABELS:
                continue
            table_text = _table_text(item)
            if not table_text:
                continue
            flush()
            output.append(
                _page_document(
                    document,
                    page=_page_number(item),
                    text=table_text,
                    section_path=tuple(section_stack),
                    block_type="table",
                    atomic=True,
                )
            )
    flush()
    return [replace(item, block_index=index) for index, item in enumerate(output)]


def _iter_body_items(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    collections = {
        "texts": payload.get("texts", []),
        "tables": payload.get("tables", []),
        "groups": payload.get("groups", []),
    }
    visited: set[str] = set()

    def walk(reference: str) -> Iterator[tuple[str, dict[str, Any]]]:
        if reference in visited:
            return
        visited.add(reference)
        parts = reference.strip("#/").split("/")
        if len(parts) != 2 or parts[0] not in collections:
            return
        collection, raw_index = parts
        try:
            item = collections[collection][int(raw_index)]
        except (IndexError, TypeError, ValueError):
            return
        if collection == "groups":
            for child in item.get("children", []):
                child_ref = child.get("$ref") if isinstance(child, dict) else None
                if isinstance(child_ref, str):
                    yield from walk(child_ref)
            return
        yield collection.removesuffix("s"), item

    for child in payload.get("body", {}).get("children", []):
        reference = child.get("$ref") if isinstance(child, dict) else None
        if isinstance(reference, str):
            yield from walk(reference)


def _table_text(item: dict[str, Any]) -> str:
    data = item.get("data") or {}
    cells = data.get("table_cells") or []
    if not cells:
        return ""
    row_count = max((int(cell.get("end_row_offset_idx", 0)) for cell in cells), default=0)
    col_count = max((int(cell.get("end_col_offset_idx", 0)) for cell in cells), default=0)
    if row_count <= 0 or col_count <= 0:
        return ""
    grid = [["" for _ in range(col_count)] for _ in range(row_count)]
    for cell in cells:
        row = int(cell.get("start_row_offset_idx", 0))
        column = int(cell.get("start_col_offset_idx", 0))
        if row < row_count and column < col_count:
            grid[row][column] = clean_text(str(cell.get("text", ""))).replace("\n", " ")
    rows = [" | ".join(value for value in row).strip(" |") for row in grid]
    rows = [row for row in rows if row]
    return clean_text("[表格]\n" + "\n".join(rows)) if rows else ""


def _page_number(item: dict[str, Any]) -> int | None:
    provenance = item.get("prov") or []
    if not provenance:
        return None
    value = provenance[0].get("page_no")
    return int(value) if value is not None else None


def _page_document(
    document: CorpusDocument,
    *,
    page: int | None,
    text: str,
    section_path: tuple[str, ...],
    block_type: str = "text",
    atomic: bool = False,
) -> PageDocument:
    section = " > ".join(section_path) or None
    return PageDocument(
        file_name=document.filename,
        relative_path=document.relative_path,
        page=page,
        text=text,
        source_hash=document.content_hash,
        source_type="pdf",
        corpus_source_type=document.source_type,
        source_title=document.title,
        section=section,
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
        block_type=block_type,
        atomic=atomic,
    )
