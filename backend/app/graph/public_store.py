from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from dataclasses import fields
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.graph.models import GraphEdge, GraphNode, ProvenanceRecord
from app.graph.snapshot import graph_version_directory, validate_snapshot
from app.graph.vocabulary import RELATION_LABELS
from app.rag.index_versions import read_active_pointer
from app.schemas.knowledge_graph import (
    KnowledgeGraphEdge,
    KnowledgeGraphMetaResponse,
    KnowledgeGraphNode,
    KnowledgeGraphNodeDetailResponse,
    KnowledgeGraphRelationGroup,
    KnowledgeGraphResponse,
    KnowledgeGraphSearchItem,
    KnowledgeGraphSearchResponse,
    KnowledgeGraphSource,
)


class PublicGraphUnavailable(RuntimeError):
    pass


class PublicGraphNotFound(LookupError):
    pass


class PublicGraphAmbiguous(LookupError):
    def __init__(self, candidates: list[KnowledgeGraphSearchItem]) -> None:
        self.candidates = candidates


class PublicGraphStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def meta(self) -> KnowledgeGraphMetaResponse:
        state = self._load()
        metadata = state[0]
        return KnowledgeGraphMetaResponse(
            version=metadata["graph_version"],
            knowledge_base_version=metadata["knowledge_base_version"],
            updated_at=metadata["created_at"],
            source_documents=metadata["source_documents"],
            node_count=metadata["node_count"],
            edge_count=metadata["edge_count"],
            schema_version=metadata["schema_version"],
            model=metadata["model"],
        )

    def graph(
        self,
        *,
        center: str | None,
        depth: int,
        limit: int,
        types: set[str],
        relations: set[str],
        include_sources: bool,
    ) -> KnowledgeGraphResponse:
        metadata, nodes, edges, provenance = self._load()
        selected_ids, center_id, truncated = self._select(
            nodes,
            edges,
            provenance,
            center=center,
            depth=depth,
            limit=limit,
            include_sources=include_sources,
        )
        if not include_sources:
            selected_ids = {
                node_id
                for node_id in selected_ids
                if nodes[node_id].entity_type not in {"EvidenceSource", "Guideline"}
            }
        if types:
            selected_ids = {
                node_id for node_id in selected_ids if nodes[node_id].entity_type in types
            }
        visible_edges = [
            edge
            for edge in edges.values()
            if edge.source_id in selected_ids
            and edge.target_id in selected_ids
            and (not relations or edge.relation_type in relations)
        ]
        visible_ids = {
            node_id
            for edge in visible_edges
            for node_id in (edge.source_id, edge.target_id)
        }
        if center_id in selected_ids:
            visible_ids.add(center_id)
        degree = _degrees(edges.values())
        return KnowledgeGraphResponse(
            version=metadata["graph_version"],
            knowledge_base_version=metadata["knowledge_base_version"],
            center_id=center_id,
            depth=depth,
            truncated=truncated,
            nodes=[
                _node_response(nodes[node_id], degree, provenance)
                for node_id in sorted(visible_ids)
            ],
            edges=[_edge_response(edge) for edge in sorted(visible_edges, key=lambda x: x.id)],
        )

    def search(self, query: str, limit: int) -> KnowledgeGraphSearchResponse:
        metadata, nodes, _edges, _provenance = self._load()
        needle = _normalize(query)
        ranked: list[tuple[int, str, KnowledgeGraphSearchItem]] = []
        for node in nodes.values():
            matches = [
                value
                for value in (node.canonical_name, *node.aliases)
                if needle in _normalize(value)
            ]
            if not matches:
                continue
            exact = int(any(_normalize(value) == needle for value in matches))
            alias = next((value for value in matches if value != node.canonical_name), None)
            ranked.append(
                (-exact, node.id, KnowledgeGraphSearchItem(
                    id=node.id,
                    label=node.canonical_name,
                    type=node.entity_type,
                    matched_alias=alias,
                ))
            )
        return KnowledgeGraphSearchResponse(
            version=metadata["graph_version"],
            items=[item for _exact, _id, item in sorted(ranked)[:limit]],
        )

    def detail(self, node_id: str) -> KnowledgeGraphNodeDetailResponse:
        metadata, nodes, edges, provenance = self._load()
        node = nodes.get(node_id)
        if node is None:
            raise PublicGraphNotFound(node_id)
        degree = _degrees(edges.values())
        grouped: dict[str, list[KnowledgeGraphNode]] = defaultdict(list)
        provenance_ids = set(node.provenance_ids)
        for edge in edges.values():
            if edge.source_id == node_id:
                grouped[edge.relation_type].append(
                    _node_response(nodes[edge.target_id], degree, provenance)
                )
                provenance_ids.update(edge.provenance_ids)
            elif edge.target_id == node_id:
                grouped[f"INCOMING:{edge.relation_type}"].append(
                    _node_response(nodes[edge.source_id], degree, provenance)
                )
                provenance_ids.update(edge.provenance_ids)
        groups = []
        for relation, neighbors in sorted(grouped.items()):
            incoming = relation.startswith("INCOMING:")
            raw = relation.removeprefix("INCOMING:")
            label = RELATION_LABELS[raw]
            groups.append(KnowledgeGraphRelationGroup(
                relation=relation,
                relation_label=f"被{label}" if incoming else label,
                neighbors=sorted(neighbors, key=lambda item: item.id),
            ))
        return KnowledgeGraphNodeDetailResponse(
            version=metadata["graph_version"],
            knowledge_base_version=metadata["knowledge_base_version"],
            node=_node_response(node, degree, provenance),
            relations=groups,
            sources=[
                _source_response(provenance[item])
                for item in sorted(provenance_ids)
                if item in provenance
            ],
        )

    def _load(self) -> tuple[
        dict[str, Any], dict[str, GraphNode], dict[str, GraphEdge], dict[str, ProvenanceRecord]
    ]:
        try:
            pointer = read_active_pointer(self.settings.rag_index_dir)
            index_version = pointer["index_version"]
            graph_version = pointer.get("graph_version")
            if index_version == "legacy" or not graph_version:
                raise PublicGraphUnavailable("active graph is not available")
            path = graph_version_directory(self.settings.graph_snapshot_dir, graph_version)
            metadata = validate_snapshot(path, index_version=index_version)
            if metadata["graph_version"] != graph_version:
                raise PublicGraphUnavailable("active graph version mismatch")
            nodes = {
                item["id"]: _from_mapping(GraphNode, item)
                for item in _read(path / "nodes.json")
            }
            edges = {
                item["id"]: _from_mapping(GraphEdge, item)
                for item in _read(path / "edges.json")
            }
            provenance = {
                item["id"]: _from_mapping(ProvenanceRecord, item)
                for item in _read(path / "provenance.json")
            }
            return metadata, nodes, edges, provenance
        except PublicGraphUnavailable:
            raise
        except Exception as exc:
            raise PublicGraphUnavailable("active graph is unavailable") from exc

    def _select(
        self,
        nodes,
        edges,
        provenance,
        *,
        center,
        depth,
        limit,
        include_sources,
    ):
        if center:
            center_id = _resolve_center(center, nodes)
            adjacency: dict[str, set[str]] = defaultdict(set)
            for edge in edges.values():
                adjacency[edge.source_id].add(edge.target_id)
                adjacency[edge.target_id].add(edge.source_id)
            selected: list[str] = []
            queue = deque([(center_id, 0)])
            seen = {center_id}
            while queue and len(selected) < limit:
                node_id, hops = queue.popleft()
                selected.append(node_id)
                if hops >= depth:
                    continue
                for neighbor in sorted(adjacency[node_id]):
                    if (
                        not include_sources
                        and nodes[neighbor].entity_type in {"EvidenceSource", "Guideline"}
                    ):
                        continue
                    if neighbor not in seen:
                        seen.add(neighbor)
                        queue.append((neighbor, hops + 1))
            return set(selected), center_id, bool(queue)
        degree = _degrees(edges.values())
        candidates = [
            node
            for node in nodes.values()
            if include_sources
            or node.entity_type not in {"EvidenceSource", "Guideline"}
        ]
        ranked = sorted(
            candidates,
            key=lambda node: (
                -max(
                    (
                        provenance[item].authority_level
                        for item in node.provenance_ids
                        if item in provenance
                    ),
                    default=0,
                ),
                -degree.get(node.id, 0),
                node.id,
            ),
        )
        return {node.id for node in ranked[:limit]}, None, len(ranked) > limit


def _resolve_center(value: str, nodes: dict[str, GraphNode]) -> str:
    if value in nodes:
        return value
    normalized = _normalize(value)
    matches = [node for node in nodes.values() if any(
        _normalize(candidate) == normalized for candidate in (node.canonical_name, *node.aliases)
    )]
    if not matches:
        raise PublicGraphNotFound(value)
    if len(matches) > 1:
        raise PublicGraphAmbiguous([
            KnowledgeGraphSearchItem(id=node.id, label=node.canonical_name, type=node.entity_type)
            for node in sorted(matches, key=lambda item: item.id)
        ])
    return matches[0].id


def _degrees(edges) -> dict[str, int]:
    result: dict[str, int] = defaultdict(int)
    for edge in edges:
        result[edge.source_id] += 1
        result[edge.target_id] += 1
    return result


def _node_response(node, degree, provenance) -> KnowledgeGraphNode:
    return KnowledgeGraphNode(
        id=node.id,
        label=node.canonical_name,
        type=node.entity_type,
        aliases=list(node.aliases),
        degree=degree.get(node.id, 0),
        source_count=len(
            {
                provenance[item].doc_id
                for item in node.provenance_ids
                if item in provenance
            }
        ),
    )


def _edge_response(edge: GraphEdge) -> KnowledgeGraphEdge:
    return KnowledgeGraphEdge(
        id=edge.id,
        source=edge.source_id,
        target=edge.target_id,
        relation=edge.relation_type,
        relation_label=RELATION_LABELS[edge.relation_type],
        confidence=edge.confidence,
        source_count=len(edge.provenance_ids),
        visual_only=edge.visual_only,
    )


def _source_response(value: ProvenanceRecord) -> KnowledgeGraphSource:
    return KnowledgeGraphSource(
        file_name=value.file_name,
        page=value.page,
        section=value.section,
        source_type=value.source_type,
        source_url=value.source_url,
        quote=value.quote,
        chunk_id=value.chunk_id,
    )


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _from_mapping(model, values):
    normalized = dict(values)
    for item in fields(model):
        if item.name in {"aliases", "provenance_ids"}:
            normalized[item.name] = tuple(normalized.get(item.name) or ())
    return model(**normalized)
