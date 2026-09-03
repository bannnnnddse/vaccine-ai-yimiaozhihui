from __future__ import annotations

import re
from hashlib import sha256

from app.rag.models import PageDocument, TextChunk
from app.rag.text import clean_text, split_page

CHUNKING_VERSION = "structure_v2_docling"


def split_structured_document(
    document: PageDocument,
    *,
    chunk_size: int,
    chunk_overlap: int,
    start_index: int,
    atomic_max_chars: int | None = None,
) -> list[TextChunk]:
    """Prefer semantic blocks/paragraphs; use the legacy splitter only for long blocks."""
    text = clean_text(document.text)
    if not text:
        return []
    atomic_limit = atomic_max_chars or chunk_size * 2
    if document.atomic:
        parts = _split_atomic_table(text, atomic_limit)
        return [
            _make_chunk(document, part, start_index + offset, offset)
            for offset, part in enumerate(parts)
            if part.strip()
        ]
    if len(text) <= chunk_size:
        return [_make_chunk(document, text, start_index, 0)]

    paragraphs = [clean_text(value) for value in re.split(r"\n{2,}", text) if value.strip()]
    if len(paragraphs) <= 1:
        return split_page(
            document,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            start_index=start_index,
        )

    groups: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                groups.append("\n\n".join(current))
                current, current_length = [], 0
            fallback_doc = PageDocument(**{
                field: getattr(document, field)
                for field in document.__dataclass_fields__
                if field != "text"
            }, text=paragraph)
            fallback = split_page(
                fallback_doc,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                start_index=start_index + len(groups),
            )
            groups.extend(chunk.text for chunk in fallback)
            continue
        separator = 2 if current else 0
        if current and current_length + separator + len(paragraph) > chunk_size:
            groups.append("\n\n".join(current))
            current, current_length = [], 0
        current.append(paragraph)
        current_length += separator + len(paragraph)
    if current:
        groups.append("\n\n".join(current))
    return [
        _make_chunk(document, group, start_index + offset, offset)
        for offset, group in enumerate(groups)
    ]


def _split_atomic_table(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    marker = lines[0] if lines and lines[0] == "[表格]" else "[表格]"
    rows = lines[1:] if lines and lines[0] == marker else lines
    output: list[str] = []
    current = [marker]
    current_length = len(marker)
    for row in rows:
        if len(row) > limit:
            # A pathological single cell still falls back to bounded text chunks.
            if len(current) > 1:
                output.append("\n".join(current))
                current, current_length = [marker], len(marker)
            for start in range(0, len(row), max(1, limit - len(marker) - 1)):
                output.append(f"{marker}\n{row[start:start + limit - len(marker) - 1]}")
            continue
        if len(current) > 1 and current_length + 1 + len(row) > limit:
            output.append("\n".join(current))
            current, current_length = [marker], len(marker)
        current.append(row)
        current_length += 1 + len(row)
    if len(current) > 1:
        output.append("\n".join(current))
    return output


def _make_chunk(
    document: PageDocument,
    content: str,
    chunk_index: int,
    local_index: int,
) -> TextChunk:
    content = clean_text(content)
    content_hash = sha256(content.encode("utf-8")).hexdigest()
    parent_doc_id = document.doc_id or document.source_hash
    section_key = " > ".join(document.section_path) or (document.section or "")
    raw_id = (
        f"{parent_doc_id}:{document.page}:{section_key}:"
        f"{document.block_index}:{local_index}:{content_hash}"
    )
    embedding_parts = []
    if document.title:
        embedding_parts.append(f"文档：{document.title}")
    if section_key:
        embedding_parts.append(f"章节：{section_key}")
    embedding_parts.append(content)
    return TextChunk(
        id=f"chk_{sha256(raw_id.encode('utf-8')).hexdigest()[:32]}",
        file_name=document.file_name,
        relative_path=document.relative_path,
        page=document.page,
        chunk_index=chunk_index,
        text=content,
        source_hash=document.source_hash,
        source_type=document.source_type,
        corpus_source_type=document.corpus_source_type,
        source_title=document.source_title,
        source_url=document.source_url,
        section=document.section,
        parent_doc_id=parent_doc_id,
        section_path=document.section_path,
        content_hash=content_hash,
        title=document.title,
        authority_level=document.authority_level,
        evidence_level=document.evidence_level,
        publication_date=document.publication_date,
        publication_year=document.publication_year,
        effective_date=document.effective_date,
        version=document.version,
        is_superseded=document.is_superseded,
        embedding_text="\n".join(embedding_parts),
    )
