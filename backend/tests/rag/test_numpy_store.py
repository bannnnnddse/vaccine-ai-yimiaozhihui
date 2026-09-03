from pathlib import Path

import numpy as np

from app.rag.models import TextChunk
from app.rag.numpy_store import NumpyRagStore


class FakeEmbedder:
    model_name = "fake-embedding"

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[float("疫苗" in text), float("接种" in text), 1.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float("疫苗" in text), float("接种" in text), 1.0]


def _chunks() -> list[TextChunk]:
    return [
        TextChunk("id-1", "指南.pdf", "政策/指南.pdf", 12, 0, "疫苗接种", "hash-1"),
        TextChunk("id-2", "研究.pdf", "论文/研究.pdf", 3, 1, "其他内容", "hash-2"),
    ]


def test_numpy_store_persists_and_reopens(tmp_path: Path) -> None:
    NumpyRagStore(tmp_path, "test", FakeEmbedder()).rebuild(
        _chunks(), chunk_size=600, chunk_overlap=100, index_version="v2"
    )

    reopened = NumpyRagStore(tmp_path, "test", FakeEmbedder())
    reopened.validate_index(chunk_size=600, chunk_overlap=100)
    results = reopened.query("疫苗接种", fetch_k=2)

    assert reopened.inspect_index()["count"] == 2
    assert results[0].id == "id-1"
    assert results[0].page == 12
    assert np.isfinite(results[0].similarity)


def test_numpy_store_rejects_embedding_model_mismatch(tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    NumpyRagStore(tmp_path, "test", embedder).rebuild(
        _chunks(), chunk_size=600, chunk_overlap=100
    )
    embedder.model_name = "different"

    try:
        NumpyRagStore(tmp_path, "test", embedder).validate_index(
            chunk_size=600, chunk_overlap=100
        )
    except RuntimeError as exc:
        assert "embedding model mismatch" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
