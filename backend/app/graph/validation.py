from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from app.graph.builder import GRAPH_SCHEMA_VERSION
from app.graph.storage import JsonGraphStore


def validate_graph_artifacts(
    graph_dir: Path,
    *,
    index_version: str,
    chunk_catalog_path: Path,
) -> dict[str, object]:
    failures: list[str] = []
    store = JsonGraphStore(graph_dir, expected_index_version=index_version)
    manifest = store.manifest
    catalog_hash = sha256(chunk_catalog_path.read_bytes()).hexdigest()
    if manifest.get("schema_version") != GRAPH_SCHEMA_VERSION:
        failures.append("graph schema version mismatch")
    if manifest.get("chunk_catalog_hash") != catalog_hash:
        failures.append("graph chunk catalog hash mismatch")
    for name in ("nodes.json", "edges.json", "provenance.json"):
        expected = (manifest.get("files") or {}).get(name)
        actual = sha256((graph_dir / name).read_bytes()).hexdigest()
        if expected != actual:
            failures.append(f"graph file hash mismatch: {name}")
    chunk_ids = {
        json.loads(line)["id"]
        for line in chunk_catalog_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    for record in store.provenance.values():
        if record.chunk_id not in chunk_ids:
            failures.append(f"unknown provenance chunk: {record.chunk_id}")
    for edge in store.edges.values():
        if edge.source_id not in store.nodes or edge.target_id not in store.nodes:
            failures.append(f"edge references unknown node: {edge.id}")
        if not edge.provenance_ids:
            failures.append(f"edge has no provenance: {edge.id}")
        elif any(item not in store.provenance for item in edge.provenance_ids):
            failures.append(f"edge references unknown provenance: {edge.id}")
    for node in store.nodes.values():
        if not node.provenance_ids:
            failures.append(f"node has no provenance: {node.id}")
        elif any(item not in store.provenance for item in node.provenance_ids):
            failures.append(f"node references unknown provenance: {node.id}")
    if manifest.get("node_count") != len(store.nodes):
        failures.append("graph node count mismatch")
    if manifest.get("edge_count") != len(store.edges):
        failures.append("graph edge count mismatch")
    if manifest.get("provenance_count") != len(store.provenance):
        failures.append("graph provenance count mismatch")
    report = {
        "valid": not failures,
        "index_version": index_version,
        "node_count": len(store.nodes),
        "edge_count": len(store.edges),
        "provenance_count": len(store.provenance),
        "failures": failures,
    }
    if failures:
        raise ValueError("graph validation failed: " + "; ".join(failures))
    return report
