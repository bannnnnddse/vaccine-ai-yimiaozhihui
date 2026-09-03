import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from app.graph.builder import build_graph_artifacts
from app.graph.validation import validate_graph_artifacts
from app.rag.catalog import write_chunk_catalog
from app.rag.models import TextChunk


def _chunk(text: str, *, chunk_id: str = "chunk-1") -> TextChunk:
    return TextChunk(
        id=chunk_id,
        file_name="HPV指南.md",
        relative_path="指南/HPV指南.md",
        page=None,
        chunk_index=0,
        text=text,
        source_hash="source-hash",
        source_type="web",
        source_url="https://example.test/hpv",
        section="保护机制",
        parent_doc_id="doc-1",
        content_hash=sha256(text.encode("utf-8")).hexdigest(),
        authority_level=3,
    )


def test_builds_deterministic_graph_with_provenance(tmp_path: Path) -> None:
    catalog = tmp_path / "chunks.jsonl"
    chunks = [
        _chunk("HPV疫苗可预防HPV感染。"),
        replace(_chunk("HPV感染可进展为宫颈癌。"), id="chunk-2", chunk_index=1),
    ]
    write_chunk_catalog(catalog, chunks)
    catalog_hash = sha256(catalog.read_bytes()).hexdigest()
    graph_dir = tmp_path / "graph"

    manifest = build_graph_artifacts(
        chunks,
        graph_dir,
        index_version="index-v1",
        chunk_catalog_hash=catalog_hash,
    )
    report = validate_graph_artifacts(
        graph_dir,
        index_version="index-v1",
        chunk_catalog_path=catalog,
    )

    assert manifest["edge_count"] == 2
    assert report["valid"] is True
    edges = json.loads((graph_dir / "edges.json").read_text(encoding="utf-8"))
    provenance = json.loads((graph_dir / "provenance.json").read_text(encoding="utf-8"))
    assert all(item["provenance_ids"] for item in edges)
    assert {item["chunk_id"] for item in provenance} == {"chunk-1", "chunk-2"}


def test_validation_rejects_unknown_provenance_chunk(tmp_path: Path) -> None:
    catalog = tmp_path / "chunks.jsonl"
    chunk = _chunk("HPV疫苗可预防HPV感染。")
    write_chunk_catalog(catalog, [chunk])
    graph_dir = tmp_path / "graph"
    build_graph_artifacts(
        [chunk],
        graph_dir,
        index_version="index-v1",
        chunk_catalog_hash=sha256(catalog.read_bytes()).hexdigest(),
    )
    values = json.loads((graph_dir / "provenance.json").read_text(encoding="utf-8"))
    values[0]["chunk_id"] = "missing"
    (graph_dir / "provenance.json").write_text(json.dumps(values), encoding="utf-8")

    with pytest.raises(ValueError, match="graph validation failed"):
        validate_graph_artifacts(
            graph_dir,
            index_version="index-v1",
            chunk_catalog_path=catalog,
        )
