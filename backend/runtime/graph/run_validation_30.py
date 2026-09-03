from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.graph.snapshot import GraphSnapshotPipeline
from app.rag.catalog import load_chunk_catalog
from app.rag.index_versions import resolve_active_index


async def main() -> None:
    settings = get_settings().model_copy(
        update={
            "graph_extraction_batch_size": 2,
            "graph_extraction_batch_chars": 6000,
            "qwen_timeout_seconds": 180,
        }
    )
    index_dir, index_version = resolve_active_index(settings.rag_index_dir)
    chunks = load_chunk_catalog(index_dir / "chunks.jsonl")
    selected = list(chunks[:24])
    selected_ids = {chunk.id for chunk in selected}
    selected_docs = {chunk.parent_doc_id or chunk.source_hash for chunk in selected}
    keywords = ("预防", "导致", "禁忌", "风险", "免疫", "适用", "接种", "保护")
    for chunk in chunks[24:]:
        doc_id = chunk.parent_doc_id or chunk.source_hash
        if chunk.id in selected_ids or doc_id in selected_docs:
            continue
        if len(chunk.text) < 120 or not any(word in chunk.text for word in keywords):
            continue
        selected.append(chunk)
        selected_ids.add(chunk.id)
        selected_docs.add(doc_id)
        if len(selected) == 30:
            break
    if len(selected) != 30:
        raise RuntimeError(f"could not select 30 chunks: {len(selected)}")

    validation_dir = settings.graph_snapshot_dir / "validation_inputs" / "sample-30"
    validation_dir.mkdir(parents=True, exist_ok=True)
    catalog = validation_dir / "chunks.jsonl"
    catalog.write_text(
        "".join(json.dumps(asdict(chunk), ensure_ascii=False) + "\n" for chunk in selected),
        encoding="utf-8",
    )
    client = AsyncOpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        timeout=settings.qwen_timeout_seconds,
        max_retries=0,
    )
    try:
        metadata = await GraphSnapshotPipeline(settings, client).build_for_index(
            validation_dir,
            f"validation-30-{index_version}",
            force_reextract=False,
            mode="validation-30",
        )
    finally:
        await client.close()
    summary = {
        "metadata": metadata,
        "sample": [
            {
                "chunk_id": chunk.id,
                "file_name": chunk.file_name,
                "page": chunk.page,
                "section": chunk.section,
                "characters": len(chunk.text),
                "reused_expected": index < 24,
            }
            for index, chunk in enumerate(selected)
        ],
    }
    (validation_dir / "validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
