from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.graph.snapshot import GraphSnapshotPipeline
from app.rag.catalog import load_chunk_catalog
from app.rag.index_versions import resolve_active_index


SAMPLE_IDS = (
    "892cdc3bbb3ffe0731a9b6e199e6c7d505705171fae911c6118f4ffe6a285a22",
    "chk_da1813e5c197d2be1f3a6066d464ee93",
    "2ec0167a9797ad14967b6ee55f69c99ae7f4bf666c7678c06efd8391bcb6da53",
    "chk_f5945e004be88f76e9fdcd1c4ce84972",
    "a5fff5d77c308b2bd0d919e4ba99c63f057f756dedbd7abb8ad2c25ac4cb8a31",
    "chk_c6f4b20a04c62165ce4ed22bc2d20681",
    "chk_265fcc00a0e5bb68dc8df0d54fe9ea45",
    "chk_663b28192335023b4ebebd3f82739c3d",
    "chk_afe91dedf2d0077b8d9fc42ef7ba8e10",
    "chk_68d674e1bb3e75066b658dbf12ae3321",
    "chk_818b985db28e77615aadca3dae463b57",
    "d1724ee3c7a12a9d2a5a640e5d8af33c5a9561f9fe3bfe941a8d2270d158839c",
)


async def main() -> None:
    settings = get_settings().model_copy(
        update={
            "graph_extraction_batch_size": 2,
            "graph_extraction_batch_chars": 6000,
            "qwen_timeout_seconds": 180,
        }
    )
    index_dir, index_version = resolve_active_index(settings.rag_index_dir)
    chunks_by_id = {chunk.id: chunk for chunk in load_chunk_catalog(index_dir / "chunks.jsonl")}
    selected = [chunks_by_id[chunk_id] for chunk_id in SAMPLE_IDS]
    validation_dir = settings.graph_snapshot_dir / "validation_inputs" / "medical-sample-12"
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "chunks.jsonl").write_text(
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
            f"validation-12-{index_version}",
            force_reextract=False,
            mode="medical-validation-12",
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
            }
            for chunk in selected
        ],
    }
    (validation_dir / "validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
