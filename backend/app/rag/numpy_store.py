from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import numpy as np

from app.rag.catalog import load_chunk_catalog, write_chunk_catalog
from app.rag.models import RetrievedChunk, TextChunk
from app.rag.store import RagIndexCorruptError, RagIndexNotReadyError

_SCHEMA_VERSION = "4"
_BACKEND = "numpy_exact_v1"
_METADATA_FILE = "dense_store.json"
_VECTORS_FILE = "vectors.npy"
_RECORDS_FILE = "dense_records.jsonl"


class NumpyRagStore:
    """Small, deterministic exact-cosine store for the frozen local corpus."""

    def __init__(self, index_dir: Path, collection_name: str, embedder) -> None:
        self._index_dir = Path(index_dir)
        self._collection_name = collection_name
        self.embedder = embedder
        self._vectors: np.ndarray | None = None
        self._chunks: list[TextChunk] | None = None

    def rebuild(
        self,
        chunks: list[TextChunk],
        *,
        chunk_size: int,
        chunk_overlap: int,
        index_version: str = "legacy",
        chunking_version: str = "fixed_v1",
        corpus_manifest_hash: str = "unknown",
    ) -> None:
        embeddings = self.embedder.embed_passages([
            chunk.embedding_text or chunk.text for chunk in chunks
        ])
        vectors = np.asarray(embeddings, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(chunks):
            raise RagIndexCorruptError("embedding matrix shape does not match chunk count")
        if not np.isfinite(vectors).all():
            raise RagIndexCorruptError("embedding matrix contains non-finite values")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise RagIndexCorruptError("embedding matrix contains zero vectors")
        vectors /= norms

        self._index_dir.mkdir(parents=True, exist_ok=True)
        vectors_path = self._index_dir / _VECTORS_FILE
        temporary_vectors = vectors_path.with_suffix(".tmp")
        try:
            with temporary_vectors.open("wb") as stream:
                np.save(stream, vectors, allow_pickle=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_vectors, vectors_path)
        finally:
            temporary_vectors.unlink(missing_ok=True)

        write_chunk_catalog(self._index_dir / _RECORDS_FILE, chunks)
        metadata = {
            "schema_version": _SCHEMA_VERSION,
            "backend": _BACKEND,
            "collection_name": self._collection_name,
            "embedding_model": self.embedder.model_name,
            "embedding_dimensions": int(vectors.shape[1]),
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "index_version": index_version,
            "chunking_version": chunking_version,
            "corpus_manifest_hash": corpus_manifest_hash,
            "count": len(chunks),
        }
        metadata_path = self._index_dir / _METADATA_FILE
        temporary_metadata = metadata_path.with_suffix(".tmp")
        try:
            temporary_metadata.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_metadata, metadata_path)
        finally:
            temporary_metadata.unlink(missing_ok=True)
        self._vectors = vectors
        self._chunks = list(chunks)

    def _metadata(self) -> dict:
        path = self._index_dir / _METADATA_FILE
        if not path.is_file():
            raise RagIndexNotReadyError("RAG index is not ready")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RagIndexCorruptError("dense store metadata is invalid") from exc

    def _load(self) -> tuple[np.ndarray, list[TextChunk]]:
        if self._vectors is not None and self._chunks is not None:
            return self._vectors, self._chunks
        try:
            vectors = np.load(self._index_dir / _VECTORS_FILE, mmap_mode="r", allow_pickle=False)
            chunks = load_chunk_catalog(self._index_dir / _RECORDS_FILE)
        except (OSError, ValueError) as exc:
            raise RagIndexCorruptError("dense store files are invalid") from exc
        if vectors.ndim != 2 or vectors.shape[0] != len(chunks):
            raise RagIndexCorruptError("dense store vector/record count mismatch")
        self._vectors = vectors
        self._chunks = chunks
        return vectors, chunks

    def validate_index(self, *, chunk_size: int, chunk_overlap: int) -> None:
        metadata = self._metadata()
        vectors, chunks = self._load()
        if metadata.get("schema_version") != _SCHEMA_VERSION:
            raise RagIndexCorruptError("RAG index schema version mismatch")
        if metadata.get("backend") != _BACKEND:
            raise RagIndexCorruptError("RAG index backend mismatch")
        if (
            self.embedder is not None
            and metadata.get("embedding_model") != self.embedder.model_name
        ):
            raise RagIndexCorruptError("RAG index embedding model mismatch")
        if int(metadata.get("chunk_size", 0)) != chunk_size:
            raise RagIndexCorruptError("RAG index chunk size mismatch")
        if int(metadata.get("chunk_overlap", -1)) != chunk_overlap:
            raise RagIndexCorruptError("RAG index chunk overlap mismatch")
        if int(metadata.get("count", -1)) != len(chunks) or vectors.shape[0] != len(chunks):
            raise RagIndexCorruptError("RAG index count mismatch")

    def query(self, query_text: str, *, fetch_k: int) -> list[RetrievedChunk]:
        if self.embedder is None:
            raise RagIndexCorruptError("query embedder is unavailable")
        vectors, chunks = self._load()
        query = np.asarray(self.embedder.embed_query(query_text), dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != vectors.shape[1] or not np.isfinite(query).all():
            raise RagIndexCorruptError("query embedding shape is invalid")
        norm = float(np.linalg.norm(query))
        if norm == 0:
            raise RagIndexCorruptError("query embedding is zero")
        similarities = np.asarray(vectors @ (query / norm))
        limit = min(fetch_k, len(chunks))
        if limit <= 0:
            return []
        # Stable ordering makes equal-score results reproducible across processes
        # and preserves catalog order as the final tie-break.
        ordered = np.argsort(-similarities, kind="stable")[:limit]
        return [
            RetrievedChunk(**asdict(chunks[int(index)]), similarity=float(similarities[index]))
            for index in ordered
        ]

    def inspect_index(self) -> dict:
        metadata = self._metadata()
        vectors, chunks = self._load()
        if vectors.shape[0] != len(chunks):
            raise RagIndexCorruptError("dense store vector/record count mismatch")
        return {"count": len(chunks), "metadata": metadata}


def is_numpy_index(index_dir: Path) -> bool:
    return (Path(index_dir) / _METADATA_FILE).is_file()
