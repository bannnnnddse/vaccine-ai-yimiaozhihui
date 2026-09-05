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
        window_max_length: int | None = None,
    ) -> None:
        self.model_name = model_name
        self._cache_dir = cache_dir
        self._device = device
        self._local_files_only = local_files_only
        self._revision = revision
        self._max_length = max_length
        self._window_max_length = window_max_length
        self._window_model = None
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

    def _ensure_window_model(self):
        if self._window_model is None:
            max_length = self._window_max_length or self._max_length
            try:
                if max_length == self._max_length:
                    self._window_model = self._model
                else:
                    options = {
                        "cache_folder": str(self._cache_dir),
                        "device": self._device,
                        "local_files_only": self._local_files_only,
                        "max_length": max_length,
                    }
                    if self._revision is not None:
                        options["revision"] = self._revision
                    self._window_model = CrossEncoder(self.model_name, **options)
            except Exception as exc:
                raise RerankerUnavailableError("window reranker model is unavailable") from exc
        return self._window_model

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        *,
        batch_size: int = 8,
        window_texts: dict[str, str] | None = None,
        window_batch_size: int | None = None,
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
        scored = normalize_reranker_scores(candidates, raw_scores)
        if window_texts:
            scored = self._apply_window_scores(
                query, scored, window_texts, window_batch_size or batch_size
            )
        return scored

    def _apply_window_scores(
        self,
        query: str,
        scored: list[RetrievedChunk],
        window_texts: dict[str, str],
        batch_size: int,
    ) -> list[RetrievedChunk]:
        from dataclasses import replace

        window_candidates = [candidate for candidate in scored if window_texts.get(candidate.id)]
        if not window_candidates:
            return scored
        pairs = [(query, window_texts[candidate.id]) for candidate in window_candidates]
        try:
            window_model = self._ensure_window_model()
            predictions = window_model.predict(
                pairs,
                batch_size=batch_size,
                show_progress_bar=False,
            )
            window_scores = [float(value) for value in predictions]
        except Exception as exc:
            raise RerankerUnavailableError("window reranker prediction failed") from exc
        window_by_id = {
            candidate.id: score
            for candidate, score in zip(window_candidates, window_scores, strict=True)
        }
        merged = [
            replace(
                candidate,
                relevance_score=max(
                    candidate.relevance_score or 0.0, window_by_id.get(candidate.id, 0.0)
                ),
            )
            for candidate in scored
        ]
        merged.sort(
            key=lambda item: (
                -(item.relevance_score or 0.0),
                item.fused_rank or 10**9,
                item.id,
            )
        )
        return merged
