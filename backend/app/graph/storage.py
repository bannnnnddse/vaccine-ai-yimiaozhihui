from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from app.graph.models import GraphEdge, GraphNode, ProvenanceRecord


class GraphStoreError(RuntimeError):
    pass


class JsonGraphStore:
    def __init__(self, graph_dir: Path, *, expected_index_version: str) -> None:
        self.graph_dir = graph_dir
        self.expected_index_version = expected_index_version
        self.manifest: dict[str, object] = {}
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        self.provenance: dict[str, ProvenanceRecord] = {}
        self._load()

    def _load(self) -> None:
        try:
            manifest_path = self.graph_dir / "manifest.json"
            if not manifest_path.is_file():
                manifest_path = self.graph_dir / "metadata.json"
            self.manifest = _read_json(manifest_path)
            bound_version = self.manifest.get(
                "index_version", self.manifest.get("knowledge_base_version")
            )
            if bound_version != self.expected_index_version:
                raise GraphStoreError("graph index version mismatch")
            self.nodes = {
                item["id"]: _from_mapping(GraphNode, item)
                for item in _read_json(self.graph_dir / "nodes.json")
            }
            self.edges = {
                item["id"]: _from_mapping(GraphEdge, item)
                for item in _read_json(self.graph_dir / "edges.json")
            }
            self.provenance = {
                item["id"]: _from_mapping(ProvenanceRecord, item)
                for item in _read_json(self.graph_dir / "provenance.json")
            }
        except GraphStoreError:
            raise
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GraphStoreError("graph artifacts are unavailable or invalid") from exc


def _read_json(path: Path):
    if not path.is_file():
        raise GraphStoreError("graph artifacts are incomplete")
    return json.loads(path.read_text(encoding="utf-8"))


def _from_mapping(model, values: dict):
    normalized = dict(values)
    for item in fields(model):
        if item.name in {"aliases", "provenance_ids"}:
            normalized[item.name] = tuple(normalized.get(item.name) or ())
    return model(**normalized)
