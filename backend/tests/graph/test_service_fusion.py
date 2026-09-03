import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from app.core.config import Settings
from app.graph.builder import build_graph_artifacts
from app.graph.fusion import fuse_retrieval_context
from app.graph.models import GraphRetrievalResult
from app.graph.service import GraphService
from app.rag.catalog import write_chunk_catalog
from app.rag.models import RagSource, RetrievedChunk, TextChunk
from app.rag.service import RetrievalResult


def _text_chunk(chunk_id: str, text: str, index: int) -> TextChunk:
    return TextChunk(
        id=chunk_id,
        file_name="HPV指南.md",
        relative_path="指南/HPV指南.md",
        page=None,
        chunk_index=index,
        text=text,
        source_hash="source-hash",
        source_type="web",
        source_url="https://example.test/hpv",
        section="机制",
        parent_doc_id="doc-1",
        content_hash=sha256(text.encode("utf-8")).hexdigest(),
        authority_level=3,
    )


def _graph_service(tmp_path: Path) -> GraphService:
    index_dir = tmp_path / "rag_index" / "versions" / "index-v1"
    chunks = [
        _text_chunk("chunk-1", "HPV疫苗可预防HPV感染。", 0),
        _text_chunk("chunk-2", "HPV感染可进展为宫颈癌。", 1),
    ]
    catalog = index_dir / "chunks.jsonl"
    write_chunk_catalog(catalog, chunks)
    graph_manifest = build_graph_artifacts(
        chunks,
        index_dir / "graph",
        index_version="index-v1",
        chunk_catalog_hash=sha256(catalog.read_bytes()).hexdigest(),
    )
    graph_manifest_path = index_dir / "graph" / "manifest.json"
    (index_dir / "manifest.json").write_text(
        json.dumps(
            {
                "index_version": "index-v1",
                "chunk_catalog_hash": sha256(catalog.read_bytes()).hexdigest(),
                "graph": {
                    "schema_version": graph_manifest["schema_version"],
                    "extraction_rules_version": graph_manifest[
                        "extraction_rules_version"
                    ],
                    "manifest_sha256": sha256(graph_manifest_path.read_bytes()).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        rag_index_dir=tmp_path / "rag_index",
        graph_rag_enabled=True,
        graph_extraction_rules_version=graph_manifest["extraction_rules_version"],
    )
    return GraphService.for_index_version(settings, "index-v1")


def test_retrieves_two_hop_path_with_provenance(tmp_path: Path) -> None:
    result = _graph_service(tmp_path).retrieve("HPV疫苗为什么能降低宫颈癌风险？")

    assert result.trace["status"] == "retrieved"
    assert any(len(path.edges) == 2 for path in result.paths)
    assert "chunk_id=" in result.context
    assert {item.content for item in result.sources} >= {
        "HPV疫苗可预防HPV感染。",
        "HPV感染可进展为宫颈癌。",
    }


def test_direct_schedule_question_stays_vector_only(tmp_path: Path) -> None:
    result = _graph_service(tmp_path).retrieve("HPV疫苗需要打几针？")

    assert result.paths == []
    assert result.trace["status"] == "not_applicable"


def test_runtime_rejects_graph_file_hash_mismatch(tmp_path: Path) -> None:
    service = _graph_service(tmp_path)
    graph_dir = tmp_path / "rag_index" / "versions" / "index-v1" / "graph"
    (graph_dir / "nodes.json").write_text("[]", encoding="utf-8")

    try:
        service.retrieve("HPV疫苗为什么能降低宫颈癌风险？")
    except ValueError as exc:
        assert "graph file hash mismatch" in str(exc)
    else:
        raise AssertionError("corrupt runtime graph must be rejected")


def test_fusion_preserves_chunks_and_deduplicates_sources() -> None:
    base = _text_chunk("chunk-1", "HPV疫苗可预防HPV感染。", 0)
    chunk = RetrievedChunk(**asdict(base), similarity=0.9)
    source = RagSource(
        file_name=base.file_name,
        page=base.page,
        content=base.text,
        source_type=base.source_type,
        source_url=base.source_url,
        section=base.section,
    )
    vector = RetrievalResult([chunk], "old-context", [source])
    graph = GraphRetrievalResult(paths=[object()], context="<graph_knowledge />", sources=[source])

    fused = fuse_retrieval_context(vector, graph, max_context_chars=1000)

    assert fused.chunks == vector.chunks
    assert "<knowledge " in fused.context
    assert "<graph_knowledge" in fused.context
    assert len(fused.sources) == 1


def test_no_graph_paths_returns_original_retrieval() -> None:
    vector = RetrievalResult([], "unchanged", [])

    assert fuse_retrieval_context(
        vector,
        GraphRetrievalResult(),
        max_context_chars=1000,
    ) is vector
