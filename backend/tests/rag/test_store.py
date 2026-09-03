from pathlib import Path

from app.rag.models import TextChunk
from app.rag.store import ChromaRagStore


class FakeEmbedder:
    model_name = "fake-embedding"

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[float("疫苗" in text), float("接种" in text), 1.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float("疫苗" in text), float("接种" in text), 1.0]


def _chunk() -> TextChunk:
    return TextChunk("id-1", "指南.pdf", "政策/指南.pdf", 12, 3, "疫苗接种注意事项", "hash")


def test_store_persists_documents_and_metadata(tmp_path: Path) -> None:
    first = ChromaRagStore(tmp_path, "test_collection", FakeEmbedder())
    first.rebuild([_chunk()], chunk_size=600, chunk_overlap=100)

    second = ChromaRagStore(tmp_path, "test_collection", FakeEmbedder())
    results = second.query("疫苗接种", fetch_k=1)

    assert len(results) == 1
    assert results[0].file_name == "指南.pdf"
    assert results[0].page == 12
    assert results[0].chunk_index == 3
    assert results[0].text == "疫苗接种注意事项"


def test_store_rejects_model_mismatch(tmp_path: Path) -> None:
    store = ChromaRagStore(tmp_path, "test_collection", FakeEmbedder())
    store.rebuild([_chunk()], chunk_size=600, chunk_overlap=100)
    store.embedder.model_name = "different-model"

    try:
        store.validate_index(chunk_size=600, chunk_overlap=100)
    except RuntimeError as exc:
        assert "embedding model mismatch" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
