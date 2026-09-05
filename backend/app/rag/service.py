import html
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from app.core.config import Settings
from app.core.observability import timed_stage
from app.rag.catalog import load_chunk_catalog
from app.rag.embeddings import BgeEmbedder
from app.rag.hybrid import Bm25Index, reciprocal_rank_fusion
from app.rag.index_versions import resolve_active_index, version_directory
from app.rag.models import RagSource, RetrievedChunk
from app.rag.numpy_store import NumpyRagStore, is_numpy_index
from app.rag.ranking import apply_quality_prior, select_diverse_diversity_first
from app.rag.reranker import CrossEncoderReranker, RerankerUnavailableError
from app.rag.store import ChromaRagStore

logger = logging.getLogger(__name__)
RagProgressCallback = Callable[[str], None]


def _report_progress(callback: RagProgressCallback | None, stage: str) -> None:
    if callback is not None:
        callback(stage)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    context: str
    sources: list[RagSource]


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    pipeline: str
    dense: list[RetrievedChunk]
    lexical: list[RetrievedChunk]
    fused: list[RetrievedChunk]
    reranked: list[RetrievedChunk]
    quality_adjusted: list[RetrievedChunk]
    selected: list[RetrievedChunk]
    timings_ms: dict[str, float]
    fallback_reason: str | None = None


class RagService:
    def __init__(
        self,
        settings: Settings,
        store: ChromaRagStore | None = None,
        *,
        index_path_override: Path | None = None,
        index_version_override: str | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._injected_store = store is not None
        self._index_path_override = index_path_override
        self._index_version_override = index_version_override
        self._active_index_path: Path | None = index_path_override
        self._active_index_version: str | None = index_version_override
        self._bm25: Bm25Index | None = None
        self._catalog_chunks: list | None = None
        self._catalog_by_key: dict[tuple[str | None, int], object] = {}
        self._reranker: CrossEncoderReranker | None = None
        self._reranker_failed = False
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> "RagService":
        return cls(settings)

    @classmethod
    def for_index_version(cls, settings: Settings, index_version: str) -> "RagService":
        return cls(
            settings,
            index_path_override=version_directory(settings.rag_index_dir, index_version),
            index_version_override=index_version,
        )

    def _ensure_store(self) -> ChromaRagStore:
        if self._injected_store and self._store is not None:
            return self._store
        if (
            self._store is not None
            and self._active_index_path is None
            and self._index_path_override is None
        ):
            # Preserve the existing injectable store boundary used by offline tests.
            return self._store
        if self._index_path_override is not None and self._index_version_override is not None:
            active_path = self._index_path_override
            active_version = self._index_version_override
        else:
            active_path, active_version = resolve_active_index(self._settings.rag_index_dir)
        if (
            self._store is not None
            and self._active_index_path == active_path
            and self._active_index_version == active_version
        ):
            return self._store
        with self._lock:
            if (
                self._store is None
                or self._active_index_path != active_path
                or self._active_index_version != active_version
            ):
                embedder_options = {"local_files_only": True}
                if self._settings.rag_embedding_revision is not None:
                    embedder_options["revision"] = self._settings.rag_embedding_revision
                embedder = BgeEmbedder(
                    self._settings.rag_embedding_model,
                    self._settings.rag_model_cache_dir,
                    self._settings.rag_embedding_device,
                    **embedder_options,
                )
                store_type = NumpyRagStore if is_numpy_index(active_path) else ChromaRagStore
                self._store = store_type(active_path, self._settings.rag_collection_name, embedder)
                self._active_index_path = active_path
                self._active_index_version = active_version
                self._bm25 = None
                self._reranker = None
                self._reranker_failed = False
        if self._store is None:  # pragma: no cover - guarded by construction above
            raise RuntimeError("RAG store initialization failed")
        return self._store

    def retrieve(
        self,
        question: str,
        *,
        progress_callback: RagProgressCallback | None = None,
    ) -> RetrievalResult:
        result, _ = self.retrieve_with_trace(question, progress_callback=progress_callback)
        return result

    def warmup(self) -> RetrievalTrace:
        """Load all local retrieval models/indexes and run one bounded inference."""

        _, trace = self.retrieve_with_trace("疫苗接种")
        return trace

    def retrieve_with_trace(
        self,
        question: str,
        *,
        progress_callback: RagProgressCallback | None = None,
    ) -> tuple[RetrievalResult, RetrievalTrace]:
        settings = self._settings
        store = self._ensure_store()
        store.validate_index(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        )
        if self._hybrid_available():
            selected, trace = self._retrieve_hybrid(
                question,
                store,
                progress_callback=progress_callback,
            )
        else:
            started = time.perf_counter()
            _report_progress(progress_callback, "dense")
            with timed_stage(logger, "rag_dense", fetch_k=settings.rag_fetch_k):
                fetched = store.query(question, fetch_k=settings.rag_fetch_k)
            selected = self._select_dense(fetched)
            trace = RetrievalTrace(
                pipeline="dense_v1",
                dense=fetched,
                lexical=[],
                fused=[],
                reranked=[],
                quality_adjusted=[],
                selected=selected,
                timings_ms={"dense": (time.perf_counter() - started) * 1000},
            )
        return self._build_result(selected), trace

    def _select_dense(self, fetched: list[RetrievedChunk]) -> list[RetrievedChunk]:
        settings = self._settings
        selected: list[RetrievedChunk] = []
        seen_ids: set[str] = set()
        for chunk in fetched:
            if chunk.similarity < settings.rag_min_similarity:
                continue
            if chunk.id in seen_ids:
                continue
            seen_ids.add(chunk.id)
            selected.append(chunk)
            if len(selected) >= settings.rag_top_k:
                break
        return selected

    def _hybrid_available(self) -> bool:
        return (
            self._settings.rag_pipeline == "hybrid_v2"
            and self._active_index_version not in {None, "legacy"}
            and self._active_index_path is not None
            and (self._active_index_path / "chunks.jsonl").is_file()
        )

    def _retrieve_hybrid(
        self,
        question: str,
        store: ChromaRagStore,
        *,
        progress_callback: RagProgressCallback | None = None,
    ) -> tuple[list[RetrievedChunk], RetrievalTrace]:
        settings = self._settings
        timings: dict[str, float] = {}
        started = time.perf_counter()
        _report_progress(progress_callback, "dense")
        with timed_stage(logger, "rag_dense", fetch_k=settings.rag_dense_fetch_k):
            dense = store.query(question, fetch_k=settings.rag_dense_fetch_k)
        timings["dense"] = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        _report_progress(progress_callback, "bm25")
        with timed_stage(logger, "rag_bm25", fetch_k=settings.rag_lexical_fetch_k):
            bm25 = self._ensure_bm25()
            lexical = bm25.query(question, top_k=settings.rag_lexical_fetch_k)
        timings["lexical"] = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        fused = reciprocal_rank_fusion(
            dense,
            lexical,
            rrf_k=settings.rag_rrf_k,
            limit=settings.rag_fusion_candidate_k,
        )
        timings["fusion"] = (time.perf_counter() - started) * 1000
        if settings.rag_reranker_enabled:
            try:
                started = time.perf_counter()
                rerank_candidates = fused[: settings.rag_rerank_candidate_k]
                _report_progress(progress_callback, "reranker")
                rerank_kwargs: dict[str, object] = {
                    "batch_size": settings.rag_reranker_batch_size,
                }
                window_texts = self._build_window_texts(rerank_candidates)
                if window_texts is not None:
                    rerank_kwargs["window_texts"] = window_texts
                    rerank_kwargs["window_batch_size"] = settings.rag_window_reranker_batch_size
                with timed_stage(
                    logger,
                    "rag_reranker",
                    candidates=len(rerank_candidates),
                    batch_size=settings.rag_reranker_batch_size,
                    window_rescore=bool(window_texts),
                ):
                    reranked_pool = self._ensure_reranker().rerank(
                        question,
                        rerank_candidates,
                        **rerank_kwargs,
                    )
                reranked_pool = self._smooth_neighbor_scores(
                    reranked_pool,
                    settings.rag_neighbor_smooth_lambda,
                )
                reranked = reranked_pool
                timings["reranker"] = (time.perf_counter() - started) * 1000
            except RerankerUnavailableError:
                logger.warning("RAG reranker unavailable; falling back to dense retrieval")
                self._reranker_failed = True
                selected = self._select_dense(dense)
                return selected, RetrievalTrace(
                    pipeline="dense_v1_fallback",
                    dense=dense,
                    lexical=lexical,
                    fused=fused,
                    reranked=[],
                    quality_adjusted=[],
                    selected=selected,
                    timings_ms=timings,
                    fallback_reason="reranker_unavailable",
                )
        else:
            # Explicitly disabled reranking is a controlled dense-v1 fallback.
            selected = self._select_dense(dense)
            return selected, RetrievalTrace(
                pipeline="dense_v1_fallback",
                dense=dense,
                lexical=lexical,
                fused=fused,
                reranked=[],
                quality_adjusted=[],
                selected=selected,
                timings_ms=timings,
                fallback_reason="reranker_disabled",
            )
        relevant = [
            candidate
            # Quality and diversity operate only on the bounded CrossEncoder
            # candidate budget so CPU cost remains predictable in production.
            for candidate in reranked_pool
            if (candidate.relevance_score or 0.0) >= settings.rag_min_relevance
        ]
        started = time.perf_counter()
        adjusted = apply_quality_prior(
            question,
            relevant,
            max_adjustment=settings.rag_quality_prior_max_adjustment,
            authority_share=settings.rag_quality_authority_share,
            freshness_max_adjustment=settings.rag_freshness_max_adjustment,
        )
        timings["quality_prior"] = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        selected = select_diverse_diversity_first(
            adjusted,
            top_k=settings.rag_top_k,
            max_chunks_per_document=settings.rag_max_chunks_per_document,
            near_duplicate_threshold=settings.rag_near_duplicate_threshold,
        )
        timings["diversity"] = (time.perf_counter() - started) * 1000
        return selected, RetrievalTrace(
            pipeline="hybrid_v2",
            dense=dense,
            lexical=lexical,
            fused=fused,
            reranked=reranked,
            quality_adjusted=adjusted,
            selected=selected,
            timings_ms=timings,
        )

    def _ensure_bm25(self) -> Bm25Index:
        if self._bm25 is None:
            with self._lock:
                if self._bm25 is None:
                    if self._active_index_path is None:
                        raise RuntimeError("active index path is unavailable")
                    chunks = load_chunk_catalog(self._active_index_path / "chunks.jsonl")
                    self._bm25 = Bm25Index(
                        chunks,
                        k1=self._settings.rag_bm25_k1,
                        b=self._settings.rag_bm25_b,
                    )
                    self._catalog_chunks = chunks
                    self._catalog_by_key = {
                        (chunk.parent_doc_id, chunk.chunk_index): chunk for chunk in chunks
                    }
        return self._bm25

    def _build_window_texts(self, candidates: list[RetrievedChunk]) -> dict[str, str] | None:
        settings = self._settings
        if not settings.rag_window_rescore_enabled:
            return None
        try:
            self._ensure_bm25()
        except RuntimeError:
            return None
        if not self._catalog_by_key:
            return None
        window_texts: dict[str, str] = {}
        for chunk in candidates:
            previous = self._catalog_by_key.get((chunk.parent_doc_id, chunk.chunk_index - 1))
            following = self._catalog_by_key.get((chunk.parent_doc_id, chunk.chunk_index + 1))
            parts = []
            if previous is not None and settings.rag_window_prev_chars:
                parts.append((previous.text or "")[-settings.rag_window_prev_chars :])
            parts.append(chunk.text or "")
            if following is not None and settings.rag_window_next_chars:
                parts.append((following.text or "")[: settings.rag_window_next_chars])
            window = "\n".join(part for part in parts if part)
            if window:
                window_texts[chunk.id] = window
        return window_texts or None

    def _smooth_neighbor_scores(
        self,
        candidates: list[RetrievedChunk],
        lam: float,
    ) -> list[RetrievedChunk]:
        if lam <= 0 or len(candidates) < 2:
            return candidates
        own = {chunk.id: (chunk.relevance_score or 0.0) for chunk in candidates}
        id_by_key = {
            (chunk.parent_doc_id, chunk.chunk_index): chunk.id for chunk in candidates
        }

        smoothed: list[RetrievedChunk] = []
        for chunk in candidates:
            eff = own[chunk.id]
            for delta in (1, -1):
                neighbor_id = id_by_key.get((chunk.parent_doc_id, chunk.chunk_index + delta))
                if neighbor_id is not None:
                    eff = max(eff, lam * own[neighbor_id])
            smoothed.append(replace(chunk, relevance_score=eff))
        smoothed.sort(
            key=lambda item: (
                -(item.relevance_score or 0.0),
                item.fused_rank or 10**9,
                item.id,
            )
        )
        return smoothed

    def _ensure_reranker(self) -> CrossEncoderReranker:
        if self._reranker_failed:
            raise RerankerUnavailableError("reranker previously failed")
        if self._reranker is None:
            with self._lock:
                if self._reranker is None:
                    reranker_options = {
                        "local_files_only": True,
                        "max_length": self._settings.rag_reranker_max_length,
                    }
                    if self._settings.rag_reranker_revision is not None:
                        reranker_options["revision"] = self._settings.rag_reranker_revision
                    reranker_options["window_max_length"] = (
                        self._settings.rag_window_reranker_max_length
                    )
                    self._reranker = CrossEncoderReranker(
                        self._settings.rag_reranker_model,
                        self._settings.rag_model_cache_dir,
                        self._settings.rag_reranker_device,
                        **reranker_options,
                    )
        return self._reranker

    def _build_result(self, selected: list[RetrievedChunk]) -> RetrievalResult:
        settings = self._settings
        sources = [
            RagSource(
                file_name=chunk.file_name,
                page=chunk.page,
                content=chunk.text,
                source_type=chunk.source_type,
                source_title=chunk.source_title,
                source_url=chunk.source_url,
                section=chunk.section,
                document_id=chunk.parent_doc_id or chunk.source_hash,
            )
            for chunk in selected
        ]
        context_parts: list[str] = []
        total_chars = 0
        for index, chunk in enumerate(selected, start=1):
            attributes = [
                f'source="{index}"',
                f'file="{html.escape(chunk.file_name, quote=True)}"',
            ]
            if chunk.page is not None:
                attributes.append(f'page="{chunk.page}"')
            if chunk.source_type != "pdf":
                attributes.append(f'type="{html.escape(chunk.source_type, quote=True)}"')
            if chunk.source_title:
                attributes.append(f'title="{html.escape(chunk.source_title, quote=True)}"')
            if chunk.section:
                attributes.append(f'section="{html.escape(chunk.section, quote=True)}"')
            block = (
                f"<knowledge {' '.join(attributes)}>\n"
                f"{html.escape(chunk.text, quote=True)}\n"
                f"</knowledge>"
            )
            if total_chars + len(block) > settings.rag_max_context_chars:
                break
            context_parts.append(block)
            total_chars += len(block)
        return RetrievalResult(
            chunks=selected,
            context="\n".join(context_parts),
            sources=sources,
        )
