import asyncio

from app.core.config import Settings
from app.graph.llm_extractor import LLMBatchExtraction, LLMGraphExtractor
from app.rag.models import TextChunk


def _chunk(identifier: str) -> TextChunk:
    return TextChunk(
        id=identifier,
        file_name="test.md",
        relative_path="test.md",
        page=None,
        chunk_index=0,
        text="同一段用于验证并发缓存安全的文本。",
        source_hash="source",
    )


class _TrackingExtractor(LLMGraphExtractor):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings, client=object())
        self.in_flight = 0
        self.max_in_flight = 0

    async def _request_batch(self, _chunks: list[TextChunk]) -> LLMBatchExtraction:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.01)
            return LLMBatchExtraction()
        finally:
            self.in_flight -= 1


def test_controlled_concurrency_writes_one_distinct_cache_file_per_chunk(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        graph_snapshot_dir=tmp_path / "graph",
        graph_extraction_batch_size=1,
        graph_extraction_batch_chars=6000,
        graph_extraction_workers=2,
    )
    chunks = [_chunk(f"chunk-{index}") for index in range(4)]
    extractor = _TrackingExtractor(settings)

    results, stats = asyncio.run(extractor.extract_chunks(chunks))

    assert [item.chunk_id for item in results] == [chunk.id for chunk in chunks]
    assert stats["reused_chunks"] == 0
    assert stats["extracted_chunks"] == 4
    assert stats["failed_chunks"] == 0
    assert extractor.max_in_flight == 2
    assert len(list((tmp_path / "graph" / "cache").glob("*.json"))) == 4

    resumed = LLMGraphExtractor(settings, client=None)
    cached_results, cached_stats = asyncio.run(resumed.extract_chunks(chunks))
    assert [item.chunk_id for item in cached_results] == [chunk.id for chunk in chunks]
    assert cached_stats["reused_chunks"] == 4
    assert cached_stats["extracted_chunks"] == 0
    assert cached_stats["failed_chunks"] == 0
