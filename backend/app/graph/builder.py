from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from app.graph.extractor import EXTRACTION_RULES_VERSION, RuleGraphExtractor
from app.graph.models import GraphEdge, GraphNode, ProvenanceRecord
from app.rag.catalog import load_chunk_catalog
from app.rag.models import TextChunk

GRAPH_SCHEMA_VERSION = "vaccine_graph_v3"


def build_graph_artifacts(
    chunks: list[TextChunk],
    graph_dir: Path,
    *,
    index_version: str,
    chunk_catalog_hash: str,
    extractor: RuleGraphExtractor | None = None,
) -> dict[str, object]:
    if graph_dir.exists():
        raise FileExistsError(f"graph artifacts already exist: {graph_dir}")
    extractor = extractor or RuleGraphExtractor()
    node_map: dict[str, GraphNode] = {}
    edge_map: dict[tuple[str, str, str], GraphEdge] = {}
    provenance_map: dict[str, ProvenanceRecord] = {}
    rejected_chunks = 0

    for chunk in chunks:
        relations = extractor.extract_relations(chunk.text)
        if not relations:
            rejected_chunks += 1
            continue
        for relation in relations:
            provenance = _provenance(chunk, relation.quote)
            provenance_map.setdefault(provenance.id, provenance)
            source = _node(relation.source, provenance.id)
            target = _node(relation.target, provenance.id)
            node_map[source.id] = _merge_node(node_map.get(source.id), source)
            node_map[target.id] = _merge_node(node_map.get(target.id), target)
            key = (source.id, relation.relation_type, target.id)
            existing = edge_map.get(key)
            if existing is None:
                edge_map[key] = GraphEdge(
                    id=_stable_id("edge", *key),
                    source_id=source.id,
                    target_id=target.id,
                    relation_type=relation.relation_type,
                    confidence=relation.confidence,
                    provenance_ids=(provenance.id,),
                )
            else:
                edge_map[key] = replace(
                    existing,
                    confidence=max(existing.confidence, relation.confidence),
                    provenance_ids=tuple(sorted({*existing.provenance_ids, provenance.id})),
                )

    nodes = sorted(node_map.values(), key=lambda item: item.id)
    edges = sorted(edge_map.values(), key=lambda item: item.id)
    provenance = sorted(provenance_map.values(), key=lambda item: item.id)
    temporary = graph_dir.with_name(f".{graph_dir.name}.tmp")
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        _write_json(temporary / "nodes.json", [asdict(item) for item in nodes])
        _write_json(temporary / "edges.json", [asdict(item) for item in edges])
        _write_json(temporary / "provenance.json", [asdict(item) for item in provenance])
        manifest: dict[str, object] = {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "extraction_rules_version": EXTRACTION_RULES_VERSION,
            "index_version": index_version,
            "chunk_catalog_hash": chunk_catalog_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "provenance_count": len(provenance),
            "chunks_seen": len(chunks),
            "chunks_without_explicit_relations": rejected_chunks,
            "files": {
                name: sha256((temporary / name).read_bytes()).hexdigest()
                for name in ("nodes.json", "edges.json", "provenance.json")
            },
        }
        _write_json(temporary / "manifest.json", manifest)
        os.replace(temporary, graph_dir)
        return manifest
    finally:
        if temporary.exists():
            for child in temporary.iterdir():
                child.unlink(missing_ok=True)
            temporary.rmdir()


def build_graph_for_index(index_dir: Path, *, index_version: str) -> dict[str, object]:
    catalog_path = index_dir / "chunks.jsonl"
    index_manifest_path = index_dir / "manifest.json"
    index_manifest = json.loads(index_manifest_path.read_text(encoding="utf-8"))
    catalog_hash = sha256(catalog_path.read_bytes()).hexdigest()
    if index_manifest.get("index_version") != index_version:
        raise ValueError("index manifest version mismatch")
    if index_manifest.get("chunk_catalog_hash") != catalog_hash:
        raise ValueError("chunk catalog hash mismatch")
    graph_manifest = build_graph_artifacts(
        load_chunk_catalog(catalog_path),
        index_dir / "graph",
        index_version=index_version,
        chunk_catalog_hash=catalog_hash,
    )
    updated = dict(index_manifest)
    updated["graph"] = {
        "schema_version": graph_manifest["schema_version"],
        "extraction_rules_version": graph_manifest["extraction_rules_version"],
        "node_count": graph_manifest["node_count"],
        "edge_count": graph_manifest["edge_count"],
        "manifest_sha256": sha256(
            (index_dir / "graph" / "manifest.json").read_bytes()
        ).hexdigest(),
    }
    temporary = index_manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, index_manifest_path)
    return graph_manifest


def _node(definition, provenance_id: str) -> GraphNode:
    return GraphNode(
        id=_stable_id("node", definition.entity_type, definition.canonical_name.casefold()),
        canonical_name=definition.canonical_name,
        entity_type=definition.entity_type,
        aliases=tuple(sorted(set(definition.aliases))),
        provenance_ids=(provenance_id,),
    )


def _merge_node(existing: GraphNode | None, incoming: GraphNode) -> GraphNode:
    if existing is None:
        return incoming
    return replace(
        existing,
        aliases=tuple(sorted({*existing.aliases, *incoming.aliases})),
        provenance_ids=tuple(sorted({*existing.provenance_ids, *incoming.provenance_ids})),
    )


def _provenance(chunk: TextChunk, quote: str) -> ProvenanceRecord:
    content_hash = chunk.content_hash or sha256(chunk.text.encode("utf-8")).hexdigest()
    identifier = _stable_id("prov", chunk.id, quote)
    return ProvenanceRecord(
        id=identifier,
        doc_id=chunk.parent_doc_id or chunk.source_hash,
        chunk_id=chunk.id,
        relative_path=chunk.relative_path,
        file_name=chunk.file_name,
        page=chunk.page,
        section=chunk.section,
        source_type=chunk.source_type,
        source_url=chunk.source_url,
        quote=quote[:1200],
        content_hash=content_hash,
        authority_level=chunk.authority_level,
    )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
