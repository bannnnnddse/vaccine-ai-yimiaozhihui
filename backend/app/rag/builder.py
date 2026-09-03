import json
import os
from datetime import datetime, timezone
from hashlib import sha256

from app.core.config import Settings
from app.graph.builder import GRAPH_SCHEMA_VERSION, build_graph_artifacts
from app.graph.extractor import EXTRACTION_RULES_VERSION
from app.rag.catalog import write_chunk_catalog
from app.rag.chunking import CHUNKING_VERSION, split_structured_document
from app.rag.corpus import load_corpus_manifest
from app.rag.docling_loader import load_docling_documents
from app.rag.embeddings import BgeEmbedder
from app.rag.index_versions import new_index_version, version_directory
from app.rag.markdown_loader import load_markdown_documents
from app.rag.numpy_store import NumpyRagStore
from app.rag.pdf_loader import load_pdf_pages
from app.rag.structured_loader import load_structured_markdown
from app.rag.text import split_page


def build_index(settings: Settings, *, local_files_only: bool = False) -> dict[str, object]:
    pages, report = load_pdf_pages(settings.rag_source_dir)
    markdown_documents, markdown_report = load_markdown_documents(settings.rag_source_dir)
    pages.extend(markdown_documents)
    report.markdown_files_seen = markdown_report.markdown_files_seen
    report.unique_markdown_files = markdown_report.unique_markdown_files
    report.duplicate_markdown_files = markdown_report.duplicate_markdown_files
    report.markdown_sections_indexed = markdown_report.markdown_sections_indexed
    report.warnings.extend(markdown_report.warnings)
    chunks = []
    for page in pages:
        chunks.extend(split_page(
            page,
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            start_index=len(chunks),
        ))
    report.chunks_indexed = len(chunks)
    embedder = BgeEmbedder(
        settings.rag_embedding_model,
        settings.rag_model_cache_dir,
        settings.rag_embedding_device,
        local_files_only=local_files_only,
    )
    NumpyRagStore(
        settings.rag_index_dir, settings.rag_collection_name, embedder
    ).rebuild(chunks, chunk_size=settings.rag_chunk_size, chunk_overlap=settings.rag_chunk_overlap)
    manifest: dict[str, object] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": settings.rag_embedding_model,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "pdf_files_seen": report.pdf_files_seen,
        "unique_pdf_files": report.unique_pdf_files,
        "duplicate_pdf_files": report.duplicate_pdf_files,
        "pages_seen": report.pages_seen,
        "pages_indexed": report.pages_indexed,
        "markdown_files_seen": report.markdown_files_seen,
        "unique_markdown_files": report.unique_markdown_files,
        "duplicate_markdown_files": report.duplicate_markdown_files,
        "markdown_sections_indexed": report.markdown_sections_indexed,
        "chunks_indexed": report.chunks_indexed,
        "warnings": report.warnings,
    }
    settings.rag_index_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = settings.rag_index_dir / "manifest.json"
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, manifest_path)
    return manifest


def build_candidate_index(
    settings: Settings,
    *,
    local_files_only: bool = False,
) -> dict[str, object]:
    manifest_bytes = settings.rag_corpus_manifest_path.read_bytes()
    corpus_manifest_hash = sha256(manifest_bytes).hexdigest()
    corpus_documents = load_corpus_manifest(settings.rag_corpus_manifest_path)
    accepted = [
        document
        for document in corpus_documents
        if not document.duplicate_of
        and document.parse_status in {"parsed", "partial", "ocr_parsed"}
        and document.source_type != "download_placeholder"
        and document.authority_level > 0
    ]
    pdf_documents, pdf_report = load_docling_documents(
        accepted,
        settings.rag_docling_artifact_dir,
    )
    markdown_documents, markdown_report = load_structured_markdown(
        settings.rag_source_dir,
        accepted,
    )
    structured_documents = [*pdf_documents, *markdown_documents]
    chunks = []
    for document in structured_documents:
        chunks.extend(
            split_structured_document(
                document,
                chunk_size=settings.rag_chunk_size,
                chunk_overlap=settings.rag_chunk_overlap,
                start_index=len(chunks),
            )
        )
    if not chunks:
        raise ValueError("candidate index has no chunks")
    chunk_ids = [chunk.id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("candidate index contains duplicate stable chunk IDs")

    index_version = new_index_version(corpus_manifest_hash)
    final_dir = version_directory(settings.rag_index_dir, index_version)
    if final_dir.exists():
        raise FileExistsError(f"index version already exists: {index_version}")
    # Build in the final, unique version directory and write manifest.json last;
    # absence of that atomic completeness marker makes a failed build non-activatable.
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir()
    catalog_path = final_dir / "chunks.jsonl"
    write_chunk_catalog(catalog_path, chunks)
    catalog_hash = sha256(catalog_path.read_bytes()).hexdigest()
    embedder = BgeEmbedder(
        settings.rag_embedding_model,
        settings.rag_model_cache_dir,
        settings.rag_embedding_device,
        local_files_only=local_files_only,
    )
    NumpyRagStore(
        final_dir,
        settings.rag_collection_name,
        embedder,
    ).rebuild(
        chunks,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        index_version=index_version,
        chunking_version=settings.rag_chunking_version,
        corpus_manifest_hash=corpus_manifest_hash,
    )
    graph_manifest = None
    if settings.graph_rag_enabled:
        if settings.graph_schema_version != GRAPH_SCHEMA_VERSION:
            raise ValueError("configured graph schema version is unsupported")
        if settings.graph_extraction_rules_version != EXTRACTION_RULES_VERSION:
            raise ValueError("configured graph extraction rules version is unsupported")
        graph_manifest = build_graph_artifacts(
            chunks,
            final_dir / "graph",
            index_version=index_version,
            chunk_catalog_hash=catalog_hash,
        )
    indexed_doc_ids = {chunk.parent_doc_id for chunk in chunks if chunk.parent_doc_id}
    warnings = [*pdf_report.warnings, *markdown_report.warnings]
    manifest: dict[str, object] = {
        "index_version": index_version,
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "candidate",
        "embedding_model": settings.rag_embedding_model,
        "dense_backend": "numpy_exact_v1",
        "chunking_version": settings.rag_chunking_version or CHUNKING_VERSION,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "corpus_manifest_hash": corpus_manifest_hash,
        "chunk_catalog_hash": catalog_hash,
        "corpus_document_count": len(corpus_documents),
        "accepted_document_count": len(accepted),
        "excluded_document_count": len(corpus_documents) - len(accepted),
        "acceptance_policy": {
            "exact_duplicates": "exclude",
            "parse_status": ["parsed", "partial", "ocr_parsed"],
            "download_placeholders": "exclude",
            "minimum_authority_level": 1,
        },
        "document_count": len(indexed_doc_ids),
        "chunk_count": len(chunks),
        "docling_files_seen": pdf_report.docling_files_seen,
        "docling_files_loaded": pdf_report.docling_files_loaded,
        "markdown_files_loaded": markdown_report.unique_markdown_files,
        "needs_review_count": sum(
            document.review_status == "needs_review" for document in accepted
        ),
        "parse_status": _count_values(corpus_documents, "parse_status"),
        "source_types": _count_values(corpus_documents, "source_type"),
        "warnings": warnings,
        "pipeline": {
            "dense_fetch_k": settings.rag_dense_fetch_k,
            "lexical_fetch_k": settings.rag_lexical_fetch_k,
            "fusion_candidate_k": settings.rag_fusion_candidate_k,
            "rrf_k": settings.rag_rrf_k,
            "reranker_model": settings.rag_reranker_model,
            "rerank_candidate_k": settings.rag_rerank_candidate_k,
            "quality_prior_max_adjustment": settings.rag_quality_prior_max_adjustment,
            "max_chunks_per_document": settings.rag_max_chunks_per_document,
        },
    }
    if graph_manifest is not None:
        manifest["graph"] = {
            "schema_version": graph_manifest["schema_version"],
            "extraction_rules_version": graph_manifest["extraction_rules_version"],
            "node_count": graph_manifest["node_count"],
            "edge_count": graph_manifest["edge_count"],
            "manifest_sha256": sha256(
                (final_dir / "graph" / "manifest.json").read_bytes()
            ).hexdigest(),
        }
    manifest_path = final_dir / "manifest.json"
    temporary_manifest = manifest_path.with_suffix(".tmp")
    try:
        temporary_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_manifest, manifest_path)
    finally:
        temporary_manifest.unlink(missing_ok=True)
    return manifest


def _count_values(documents, attribute: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for document in documents:
        value = str(getattr(document, attribute))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
