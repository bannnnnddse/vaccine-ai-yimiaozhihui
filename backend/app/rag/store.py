import json
import time

import chromadb

from app.rag.models import RetrievedChunk, TextChunk

_SCHEMA_VERSION = "3"
_SUPPORTED_SCHEMA_VERSIONS = {"2", "3"}
_BATCH_SIZE = 64
_HNSW_BATCH_SIZE = 100
_HNSW_SYNC_THRESHOLD = 100


class RagStoreError(RuntimeError):
    pass


class RagIndexNotReadyError(RagStoreError):
    pass


class RagIndexCorruptError(RagStoreError):
    pass


class ChromaRagStore:
    def __init__(
        self,
        index_dir,
        collection_name: str,
        embedder,
        *,
        persist_timeout_seconds: float = 300,
    ) -> None:
        self._index_dir = index_dir
        self._collection_name = collection_name
        self.embedder = embedder
        self._persist_timeout_seconds = persist_timeout_seconds

    def _client(self) -> chromadb.PersistentClient:
        return chromadb.PersistentClient(path=str(self._index_dir))

    def _collection(self, client: chromadb.PersistentClient):
        return client.get_or_create_collection(
            self._collection_name,
            configuration={
                "hnsw": {
                    "space": "cosine",
                    "batch_size": _HNSW_BATCH_SIZE,
                    "sync_threshold": _HNSW_SYNC_THRESHOLD,
                }
            },
        )

    def _wait_for_hnsw_snapshot(self) -> None:
        """Wait until Chroma has written a reloadable HNSW snapshot.

        Chroma accepts writes into SQLite before its background compactor has
        persisted the HNSW binary files.  Closing in that window can leave only
        ``index_metadata.pickle``, which cannot be reopened on Windows.
        """
        deadline = time.monotonic() + self._persist_timeout_seconds
        while time.monotonic() < deadline:
            for segment_dir in self._index_dir.iterdir():
                if not segment_dir.is_dir():
                    continue
                required = (
                    segment_dir / "header.bin",
                    segment_dir / "data_level0.bin",
                    segment_dir / "length.bin",
                )
                if all(path.is_file() and path.stat().st_size > 0 for path in required):
                    return
            time.sleep(0.25)
        raise RagIndexCorruptError(
            "Chroma HNSW snapshot was not persisted before the build timeout"
        )

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
        if len(embeddings) != len(chunks):
            raise RagIndexCorruptError("embedding count does not match chunk count")
        client = self._client()
        try:
            try:
                client.delete_collection(self._collection_name)
            except Exception:
                pass
            collection = self._collection(client)
            collection.modify(
                metadata={
                    "schema_version": _SCHEMA_VERSION,
                    "embedding_model": self.embedder.model_name,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "index_version": index_version,
                    "chunking_version": chunking_version,
                    "corpus_manifest_hash": corpus_manifest_hash,
                }
            )
            for start in range(0, len(chunks), _BATCH_SIZE):
                batch = chunks[start : start + _BATCH_SIZE]
                collection.add(
                    ids=[chunk.id for chunk in batch],
                    documents=[chunk.text for chunk in batch],
                    metadatas=[
                        {
                            "file_name": chunk.file_name,
                            "relative_path": chunk.relative_path,
                            "page": chunk.page or 0,
                            "chunk_index": chunk.chunk_index,
                            "source_hash": chunk.source_hash,
                            "source_type": chunk.source_type,
                            "corpus_source_type": chunk.corpus_source_type,
                            "source_title": chunk.source_title or "",
                            "source_url": chunk.source_url or "",
                            "section": chunk.section or "",
                            "parent_doc_id": chunk.parent_doc_id or "",
                            "section_path": json.dumps(chunk.section_path, ensure_ascii=False),
                            "content_hash": chunk.content_hash or "",
                            "title": chunk.title or "",
                            "authority_level": chunk.authority_level,
                            "evidence_level": chunk.evidence_level,
                            "publication_date": chunk.publication_date or "",
                            "publication_year": chunk.publication_year or 0,
                            "effective_date": chunk.effective_date or "",
                            "version": chunk.version,
                            "is_superseded": chunk.is_superseded,
                        }
                        for chunk in batch
                    ],
                    embeddings=embeddings[start : start + len(batch)],
                )
            # Exercise the vector reader before closing so an incomplete HNSW
            # compaction fails during candidate construction, not after activation.
            collection.query(
                query_embeddings=[embeddings[0]],
                n_results=1,
                include=["distances"],
            )
            if len(chunks) >= _HNSW_SYNC_THRESHOLD:
                self._wait_for_hnsw_snapshot()
        finally:
            client.close()

    def validate_index(self, *, chunk_size: int, chunk_overlap: int) -> None:
        client = self._client()
        try:
            try:
                collection = client.get_collection(self._collection_name)
            except Exception as exc:
                raise RagIndexNotReadyError("RAG index is not ready") from exc
            if collection.count() == 0:
                raise RagIndexNotReadyError("RAG index is empty")
            metadata = collection.metadata or {}
            if metadata.get("schema_version") not in _SUPPORTED_SCHEMA_VERSIONS:
                raise RagIndexCorruptError("RAG index schema version mismatch")
            if metadata.get("embedding_model") != self.embedder.model_name:
                raise RagIndexCorruptError("RAG index embedding model mismatch")
            if int(metadata.get("chunk_size", 0)) != chunk_size:
                raise RagIndexCorruptError("RAG index chunk size mismatch")
            if int(metadata.get("chunk_overlap", -1)) != chunk_overlap:
                raise RagIndexCorruptError("RAG index chunk overlap mismatch")
        finally:
            client.close()

    def query(self, query_text: str, *, fetch_k: int) -> list[RetrievedChunk]:
        client = self._client()
        try:
            try:
                collection = client.get_collection(self._collection_name)
            except Exception as exc:
                raise RagIndexNotReadyError("RAG index is not ready") from exc
            if collection.count() == 0:
                raise RagIndexNotReadyError("RAG index is empty")
            result = collection.query(
                query_embeddings=[self.embedder.embed_query(query_text)],
                n_results=min(fetch_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            chunks: list[RetrievedChunk] = []
            for chunk_id, document, metadata, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
                strict=True,
            ):
                if metadata is None:
                    raise RagIndexCorruptError("RAG index metadata missing")
                chunks.append(RetrievedChunk(
                    id=str(chunk_id),
                    file_name=str(metadata["file_name"]),
                    relative_path=str(metadata["relative_path"]),
                    page=int(metadata["page"]) or None,
                    chunk_index=int(metadata["chunk_index"]),
                    text=str(document),
                    source_hash=str(metadata["source_hash"]),
                    source_type=str(metadata.get("source_type", "pdf")),
                    corpus_source_type=str(metadata.get("corpus_source_type", "unknown")),
                    source_title=_optional_metadata(metadata, "source_title"),
                    source_url=_optional_metadata(metadata, "source_url"),
                    section=_optional_metadata(metadata, "section"),
                    parent_doc_id=_optional_metadata(metadata, "parent_doc_id"),
                    section_path=_section_path(metadata),
                    content_hash=_optional_metadata(metadata, "content_hash"),
                    title=_optional_metadata(metadata, "title"),
                    authority_level=int(metadata.get("authority_level", 0)),
                    evidence_level=str(metadata.get("evidence_level", "unknown")),
                    publication_date=_optional_metadata(metadata, "publication_date"),
                    publication_year=int(metadata.get("publication_year", 0)) or None,
                    effective_date=_optional_metadata(metadata, "effective_date"),
                    version=str(metadata.get("version", "unknown")),
                    is_superseded=bool(metadata.get("is_superseded", False)),
                    similarity=1.0 - float(distance),
                ))
            return chunks
        finally:
            client.close()

    def inspect_index(self) -> dict:
        client = self._client()
        try:
            try:
                collection = client.get_collection(self._collection_name)
            except Exception as exc:
                raise RagIndexNotReadyError("RAG index is not ready") from exc
            return {
                "count": collection.count(),
                "metadata": dict(collection.metadata or {}),
            }
        finally:
            client.close()


def _optional_metadata(metadata: dict, key: str) -> str | None:
    value = str(metadata.get(key, "")).strip()
    return value or None


def _section_path(metadata: dict) -> tuple[str, ...]:
    raw = str(metadata.get("section_path", ""))
    if not raw:
        return ()
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    return tuple(str(value) for value in values) if isinstance(values, list) else ()
