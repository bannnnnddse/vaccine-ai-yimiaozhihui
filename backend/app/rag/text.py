import re
from hashlib import sha256

from app.rag.models import PageDocument, TextChunk

_BOUNDARIES = "。！？；\n"


def clean_text(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"[\t\f\v ]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _cut_at_boundary(text: str, start: int, hard_end: int) -> int:
    boundary = max(text.rfind(mark, start, hard_end) for mark in _BOUNDARIES)
    return boundary + 1 if boundary >= start + (hard_end - start) // 2 else hard_end


def split_page(
    page: PageDocument,
    *,
    chunk_size: int,
    chunk_overlap: int,
    start_index: int,
) -> list[TextChunk]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    text = clean_text(page.text)
    chunks: list[TextChunk] = []
    start = 0
    chunk_index = start_index
    while start < len(text):
        hard_end = min(len(text), start + chunk_size)
        end = len(text) if hard_end == len(text) else _cut_at_boundary(text, start, hard_end)
        content = text[start:end].strip()
        if content:
            chunk_hash = sha256(content.encode("utf-8")).hexdigest()
            parent_doc_id = page.doc_id or page.source_hash
            section_key = " > ".join(page.section_path) or (page.section or "")
            raw_id = (
                f"{parent_doc_id}:{page.page}:{section_key}:"
                f"{page.block_index}:{start}:{chunk_hash}"
            )
            context_parts = []
            if page.title:
                context_parts.append(f"文档：{page.title}")
            if section_key:
                context_parts.append(f"章节：{section_key}")
            context_parts.append(content)
            chunks.append(TextChunk(
                id=sha256(raw_id.encode("utf-8")).hexdigest(),
                file_name=page.file_name,
                relative_path=page.relative_path,
                page=page.page,
                chunk_index=chunk_index,
                text=content,
                source_hash=page.source_hash,
                source_type=page.source_type,
                corpus_source_type=page.corpus_source_type,
                source_title=page.source_title,
                source_url=page.source_url,
                section=page.section,
                parent_doc_id=parent_doc_id,
                section_path=page.section_path,
                content_hash=chunk_hash,
                title=page.title,
                authority_level=page.authority_level,
                evidence_level=page.evidence_level,
                publication_date=page.publication_date,
                publication_year=page.publication_year,
                effective_date=page.effective_date,
                version=page.version,
                is_superseded=page.is_superseded,
                embedding_text="\n".join(context_parts),
            ))
            chunk_index += 1
        if end >= len(text):
            break
        start = max(start + 1, end - chunk_overlap)
    return chunks
