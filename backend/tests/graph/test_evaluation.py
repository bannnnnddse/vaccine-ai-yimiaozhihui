from app.graph.evaluation import benchmark_candidate_count, fixed_benchmark_sample
from app.rag.models import TextChunk


def _chunk(identifier: str, text: str) -> TextChunk:
    return TextChunk(
        id=identifier, file_name="test.md", relative_path="test.md", page=None,
        chunk_index=0, text=text, source_hash="source",
    )


def test_fixed_benchmark_sample_is_reproducible() -> None:
    chunks = [_chunk(str(index), "乙肝疫苗可预防乙型肝炎。") for index in range(120)]
    assert [item.id for item in fixed_benchmark_sample(chunks)] == [
        item.id for item in fixed_benchmark_sample(chunks)
    ]
    assert len(fixed_benchmark_sample(chunks)) == 100


def test_benchmark_candidate_count_uses_the_production_prefilter() -> None:
    chunks = [_chunk("medical", "乙肝疫苗可预防乙型肝炎。"), _chunk("admin", "目录")]
    assert benchmark_candidate_count(chunks) == 1
