import asyncio
import json

from app.graph.benchmark import BATCH_BENCHMARK_PROFILES, benchmark_profile
from app.rag.models import TextChunk


def _chunk(identifier: str, text: str) -> TextChunk:
    return TextChunk(
        id=identifier,
        file_name="test.md",
        relative_path="test.md",
        page=None,
        chunk_index=0,
        text=text,
        source_hash="source",
    )


def test_batch_benchmark_profiles_have_requested_sizes_and_budgets() -> None:
    profiles = [(item.name, item.batch_size, item.batch_chars) for item in BATCH_BENCHMARK_PROFILES]
    assert profiles == [
        ("A", 2, 6000),
        ("B", 4, 8000),
        ("C", 6, 10000),
    ]


def test_every_profile_creates_and_processes_batches() -> None:
    chunks = [_chunk(str(index), "乙肝疫苗可预防乙型肝炎。") for index in range(7)]

    async def request(_batch: list[TextChunk]) -> str:
        return '{"entities": [], "relations": []}'

    metrics = [
        asyncio.run(benchmark_profile(chunks, profile, request, min_confidence=0.85))
        for profile in BATCH_BENCHMARK_PROFILES
    ]

    assert [item.batches for item in metrics] == [4, 2, 2]
    assert [item.processed_chunks for item in metrics] == [7, 7, 7]


def test_benchmark_records_validator_quality_metrics() -> None:
    chunks = [
        _chunk("one", "乙肝疫苗可预防乙型肝炎。"),
        _chunk("two", "目录。"),
        _chunk("three", "接种单位负责行政管理。"),
    ]

    async def request(batch: list[TextChunk]) -> str:
        entities = []
        relations = []
        for chunk in batch:
            if chunk.id != "one":
                continue
            entities.extend([
                {"canonical_name": "乙肝疫苗", "entity_type": "Vaccine", "aliases": [],
                 "surface_form": "乙肝疫苗", "chunk_id": chunk.id},
                {"canonical_name": "乙型肝炎", "entity_type": "Disease", "aliases": [],
                 "surface_form": "乙型肝炎", "chunk_id": chunk.id},
            ])
            relations.append({
                "source_surface": "乙肝疫苗", "target_surface": "乙型肝炎",
                "relation_type": "PREVENTS", "evidence_quote": chunk.text,
                "confidence": 0.98, "chunk_id": chunk.id,
            })
        return json.dumps({"entities": entities, "relations": relations})

    metrics = asyncio.run(
        benchmark_profile(chunks, BATCH_BENCHMARK_PROFILES[0], request, min_confidence=0.85)
    )

    assert metrics.batches == 2
    assert metrics.processed_chunks == 3
    assert metrics.timeout_count == 0
    assert metrics.json_validation_failure_count == 0
    assert metrics.accepted_medical_relation_count == 1
