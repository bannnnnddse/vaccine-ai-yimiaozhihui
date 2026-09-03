from pathlib import Path

from sentence_transformers import SentenceTransformer

QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class BgeEmbedder:
    def __init__(
        self,
        model_name: str,
        cache_dir: Path,
        device: str,
        *,
        local_files_only: bool = False,
    ) -> None:
        self.model_name = model_name
        self._model = SentenceTransformer(
            model_name,
            cache_folder=str(cache_dir),
            device=device,
            local_files_only=local_files_only,
        )

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self._model.encode(
            QUERY_INSTRUCTION + text.strip(),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()
