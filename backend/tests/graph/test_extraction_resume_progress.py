import asyncio

from app.core.config import Settings
from app.graph.llm_extractor import GraphExtractionError, LLMBatchExtraction, LLMGraphExtractor
from app.graph.progress import GraphProgressStore
from app.rag.models import TextChunk


def _chunk(index: int) -> TextChunk:
    return TextChunk(
        id=f"chunk-{index}", file_name="test.md", relative_path="test.md", page=None,
        chunk_index=index, text=f"乙肝疫苗可预防乙型肝炎 {index}。", source_hash="source",
    )


class _InterruptingExtractor(LLMGraphExtractor):
    async def _request_batch(self, chunks: list[TextChunk]) -> LLMBatchExtraction:
        if int(chunks[0].id.removeprefix("chunk-")) >= 50:
            raise GraphExtractionError("request")
        return LLMBatchExtraction()


class _RecoveringExtractor(LLMGraphExtractor):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings, client=object())
        self.requested: list[str] = []

    async def _request_batch(self, chunks: list[TextChunk]) -> LLMBatchExtraction:
        self.requested.extend(chunk.id for chunk in chunks)
        return LLMBatchExtraction()


def test_resume_skips_cached_half_and_persists_progress(tmp_path) -> None:
    settings = Settings(
        _env_file=None, graph_snapshot_dir=tmp_path / "graph", graph_extraction_batch_size=1,
        graph_extraction_workers=2,
    )
    chunks = [_chunk(index) for index in range(100)]
    interrupted = _InterruptingExtractor(settings, client=object())
    first_results, first_stats = asyncio.run(interrupted.extract_chunks(chunks))
    assert len(first_results) == 50
    assert first_stats["failed_chunks"] == 50

    snapshots = []

    async def persist(progress):
        snapshots.append(progress)
        GraphProgressStore(settings.graph_snapshot_dir).write("resume-test", progress)

    resumed = _RecoveringExtractor(settings)
    second_results, second_stats = asyncio.run(
        resumed.extract_chunks(chunks, progress_callback=persist)
    )
    assert len(second_results) == 100
    assert second_stats["reused_chunks"] == 50
    assert second_stats["extracted_chunks"] == 50
    assert len(resumed.requested) == 50
    assert snapshots[-1].processed_chunks == 100
    assert (tmp_path / "graph" / "progress" / "resume-test.json").is_file()
