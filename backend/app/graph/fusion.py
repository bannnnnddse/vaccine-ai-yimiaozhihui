from __future__ import annotations

import html

from app.graph.models import GraphRetrievalResult
from app.rag.models import RagSource, RetrievedChunk
from app.rag.service import RetrievalResult


def fuse_retrieval_context(
    vector: RetrievalResult,
    graph: GraphRetrievalResult,
    *,
    max_context_chars: int,
) -> RetrievalResult:
    if not graph.context or not graph.paths:
        return vector
    graph_context = graph.context[:max_context_chars]
    vector_budget = max(max_context_chars - len(graph_context) - 1, 0)
    vector_context = _render_vector_context(vector.chunks, vector_budget)
    context = "\n".join(part for part in (vector_context, graph_context) if part)
    return RetrievalResult(
        chunks=vector.chunks,
        context=context,
        sources=_merge_sources(vector.sources, graph.sources),
    )


def _render_vector_context(chunks: list[RetrievedChunk], budget: int) -> str:
    blocks: list[str] = []
    used = 0
    for index, chunk in enumerate(chunks, start=1):
        attributes = [
            f'source="{index}"',
            f'file="{html.escape(chunk.file_name, quote=True)}"',
        ]
        if chunk.page is not None:
            attributes.append(f'page="{chunk.page}"')
        if chunk.source_type != "pdf":
            attributes.append(f'type="{html.escape(chunk.source_type, quote=True)}"')
        if chunk.source_title:
            attributes.append(f'title="{html.escape(chunk.source_title, quote=True)}"')
        if chunk.section:
            attributes.append(f'section="{html.escape(chunk.section, quote=True)}"')
        block = (
            f"<knowledge {' '.join(attributes)}>\n"
            f"{html.escape(chunk.text, quote=True)}\n"
            "</knowledge>"
        )
        if used + len(block) > budget:
            break
        blocks.append(block)
        used += len(block)
    return "\n".join(blocks)


def _merge_sources(vector: list[RagSource], graph: list[RagSource]) -> list[RagSource]:
    merged: list[RagSource] = []
    seen: set[tuple[str, int | None, str | None, str | None, str]] = set()
    for item in [*vector, *graph]:
        key = (item.file_name, item.page, item.section, item.source_url, item.content)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged
