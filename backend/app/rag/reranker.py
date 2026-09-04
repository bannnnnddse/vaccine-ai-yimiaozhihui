from __future__ import annotations

from pathlib import Path

from sentence_transformers import CrossEncoder

from app.rag.models import RetrievedChunk
from app.rag.ranking import normalize_reranker_scores


class RerankerUnavailableError(RuntimeError):
    pass


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str,
        cache_dir: Path,
        device: str,
        *,
        local_files_only: bool,
        revision: str | None = None,
        max_length: int = 512,
    ) -> None:
        self.model_name = model_name
        try:
            options = {
                "cache_folder": str(cache_dir),
                "device": device,
                "local_files_only": local_files_only,
                "max_length": max_length,
            }
            if revision is not None:
                options["revision"] = revision
            self._model = CrossEncoder(
                model_name,
                **options,
            )
        except Exception as exc:
            raise RerankerUnavailableError("reranker model is unavailable") from exc

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        *,
        batch_size: int = 8,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        pairs = [
            (query, candidate.embedding_text or candidate.text)
            for candidate in candidates
        ]
        try:
            predictions = self._model.predict(
                pairs,
                batch_size=batch_size,
                show_progress_bar=False,
            )
            raw_scores = [float(value) for value in predictions]
        except Exception as exc:
            raise RerankerUnavailableError("reranker prediction failed") from exc
        return normalize_reranker_scores(candidates, raw_scores)
