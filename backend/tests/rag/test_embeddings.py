from pathlib import Path

from app.rag import embeddings


def test_embedder_supports_offline_loading(monkeypatch, tmp_path: Path) -> None:
    class OfflineSentenceTransformer:
        def __init__(
            self,
            model_name: str,
            *,
            cache_folder: str,
            device: str,
            local_files_only: bool,
        ) -> None:
            if not local_files_only:
                raise ConnectionError("network access attempted")

    monkeypatch.setattr(embeddings, "SentenceTransformer", OfflineSentenceTransformer)

    embeddings.BgeEmbedder(
        "BAAI/bge-small-zh-v1.5",
        tmp_path,
        "cpu",
        local_files_only=True,
    )
