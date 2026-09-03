from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.core.config import Settings
from app.graph.builder import GRAPH_SCHEMA_VERSION
from app.graph.candidate_filter import filter_candidate_chunks
from app.graph.llm_extractor import LLMGraphExtractor, ValidatedChunkExtraction
from app.graph.models import GraphEdge, GraphNode, ProvenanceRecord
from app.graph.semantica_adapter import SemanticaGraphBuilderAdapter
from app.rag.catalog import load_chunk_catalog
from app.rag.models import TextChunk

SEMANTICA_VERSION = "0.6.5"


class GraphSnapshotError(RuntimeError):
    pass


def graph_version_directory(root: Path, graph_version: str) -> Path:
    if not graph_version or any(value in graph_version for value in ("/", "\\", "..")):
        raise ValueError("unsafe graph version")
    return root / "versions" / graph_version


class GraphSnapshotPipeline:
    def __init__(
        self,
        settings: Settings,
        client: AsyncOpenAI | None,
        *,
        semantica: SemanticaGraphBuilderAdapter | None = None,
    ) -> None:
        self.settings = settings
        self.extractor = LLMGraphExtractor(settings, client)
        self.semantica = semantica

    async def build_for_index(
        self,
        index_dir: Path,
        index_version: str,
        *,
        parent_graph_version: str | None = None,
        force_reextract: bool = False,
        mode: str = "incremental",
        progress_callback=None,
    ) -> dict[str, Any]:
        catalog = index_dir / "chunks.jsonl"
        if not catalog.is_file():
            raise FileNotFoundError("candidate chunk catalog is unavailable")
        chunks = load_chunk_catalog(catalog)
        candidates = filter_candidate_chunks(chunks)
        extractions, stats = await self.extractor.extract_chunks(
            candidates.candidates,
            force=force_reextract,
            total_chunks=len(chunks),
            progress_callback=progress_callback,
        )
        stats = {
            **stats,
            "candidate_count": candidates.candidate_count,
            "filtered_count": candidates.filtered_count,
            "filter_reasons": candidates.filter_reasons,
        }
        if stats.get("failed_chunks", 0):
            raise GraphSnapshotError(
                "graph extraction has failed chunks; resume before snapshot build"
            )
        node_map, edge_map, provenance_map = _aggregate(
            chunks,
            extractions,
            visual_max_per_chunk=self.settings.graph_visual_association_max_per_chunk,
            visual_max_degree=self.settings.graph_visual_association_max_degree,
        )
        entities = [
            {
                "id": node.id,
                "name": node.canonical_name,
                "type": node.entity_type,
                "confidence": 1.0,
            }
            for node in node_map.values()
        ]
        relationships = [
            {
                "source": edge.source_id,
                "target": edge.target_id,
                "type": edge.relation_type,
                "confidence": edge.confidence,
            }
            for edge in edge_map.values()
            if not edge.visual_only
        ]
        if self.semantica is None:
            self.semantica = SemanticaGraphBuilderAdapter()
        self.semantica.build(entities, relationships)
        catalog_hash = hashlib.sha256(catalog.read_bytes()).hexdigest()
        signature = hashlib.sha256(
            "\x1f".join(
                (
                    self.settings.effective_graph_extraction_model,
                    self.settings.graph_extraction_prompt_version,
                    GRAPH_SCHEMA_VERSION,
                    self.settings.graph_validator_version,
                )
            ).encode("utf-8")
        ).hexdigest()
        timestamp = datetime.now(timezone.utc)
        graph_version = (
            f"graph-{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}-"
            f"{catalog_hash[:8]}-{signature[:8]}"
        )
        target = graph_version_directory(self.settings.graph_snapshot_dir, graph_version)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.mkdir(parents=True, exist_ok=False)
        try:
            _write_json(temporary / "nodes.json", [asdict(value) for value in _sorted(node_map)])
            _write_json(temporary / "edges.json", [asdict(value) for value in _sorted(edge_map)])
            _write_json(
                temporary / "provenance.json",
                [asdict(value) for value in _sorted(provenance_map)],
            )
            extraction_report = {
                **stats,
                "rejected_relations": sum(len(item.rejected) for item in extractions),
                "rejected_chunks": sum(bool(item.rejected) for item in extractions),
                "failed_chunks": 0,
                "chunks": [
                    {
                        "chunk_id": item.chunk_id,
                        "content_hash": item.content_hash,
                        "relations": len(item.relations),
                        "rejected": item.rejected,
                    }
                    for item in extractions
                ],
            }
            _write_json(temporary / "extraction_report.json", extraction_report)
            source_documents = len({chunk.parent_doc_id or chunk.source_hash for chunk in chunks})
            metadata: dict[str, Any] = {
                "graph_version": graph_version,
                "knowledge_base_version": index_version,
                "parent_graph_version": parent_graph_version,
                "created_at": timestamp.isoformat(),
                "source_documents": source_documents,
                "source_chunks": len(chunks),
                "node_count": len(node_map),
                "edge_count": len(edge_map),
                "provenance_count": len(provenance_map),
                "schema_version": GRAPH_SCHEMA_VERSION,
                "model": self.settings.effective_graph_extraction_model,
                "prompt_version": self.settings.graph_extraction_prompt_version,
                "validator_version": self.settings.graph_validator_version,
                "semantica_version": SEMANTICA_VERSION,
                "chunk_catalog_hash": catalog_hash,
                "build_mode": mode,
                "rejected_chunks": extraction_report["rejected_chunks"],
                "failed_chunks": 0,
                **stats,
            }
            metadata["files"] = {
                name: hashlib.sha256((temporary / name).read_bytes()).hexdigest()
                for name in (
                    "nodes.json",
                    "edges.json",
                    "provenance.json",
                    "extraction_report.json",
                )
            }
            _write_json(temporary / "metadata.json", metadata)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        validate_snapshot(target, index_version=index_version)
        return metadata


def validate_snapshot(snapshot_dir: Path, *, index_version: str) -> dict[str, Any]:
    try:
        metadata = _read_json(snapshot_dir / "metadata.json")
        if metadata.get("knowledge_base_version") != index_version:
            raise GraphSnapshotError("graph snapshot knowledge-base version mismatch")
        data = {
            name: _read_json(snapshot_dir / name)
            for name in ("nodes.json", "edges.json", "provenance.json")
        }
        for name, expected in (metadata.get("files") or {}).items():
            actual = hashlib.sha256((snapshot_dir / name).read_bytes()).hexdigest()
            if actual != expected:
                raise GraphSnapshotError(f"graph snapshot file hash mismatch: {name}")
        nodes = {item["id"] for item in data["nodes.json"]}
        provenance = {item["id"] for item in data["provenance.json"]}
        for edge in data["edges.json"]:
            if edge["source_id"] not in nodes or edge["target_id"] not in nodes:
                raise GraphSnapshotError("graph edge references unknown node")
            if not edge["provenance_ids"] or any(
                item not in provenance for item in edge["provenance_ids"]
            ):
                raise GraphSnapshotError("graph edge provenance is invalid")
        if metadata.get("node_count") != len(nodes):
            raise GraphSnapshotError("graph node count mismatch")
        if metadata.get("edge_count") != len(data["edges.json"]):
            raise GraphSnapshotError("graph edge count mismatch")
        return metadata
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, GraphSnapshotError):
            raise
        raise GraphSnapshotError("graph snapshot is unavailable or invalid") from exc


def _aggregate(
    chunks: list[TextChunk],
    extractions: list[ValidatedChunkExtraction],
    *,
    visual_max_per_chunk: int = 2,
    visual_max_degree: int = 3,
) -> tuple[dict[str, GraphNode], dict[str, GraphEdge], dict[str, ProvenanceRecord]]:
    chunk_map = {chunk.id: chunk for chunk in chunks}
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}
    provenance: dict[str, ProvenanceRecord] = {}
    entities_by_chunk: dict[str, list[GraphNode]] = {}
    for extraction in extractions:
        chunk = chunk_map[extraction.chunk_id]
        chunk_entities: list[GraphNode] = []
        for entity in extraction.entities:
            # A shared chunk-level record allows visual-only association edges
            # to retain a common, inspectable source without implying a claim.
            record = _provenance(chunk, chunk.text)
            provenance[record.id] = record
            node = _node(
                entity.canonical_name,
                entity.entity_type,
                entity.aliases,
                record.id,
            )
            nodes[node.id] = _merge_node(nodes.get(node.id), node)
            chunk_entities.append(node)
        entities_by_chunk[chunk.id] = chunk_entities
        for relation in extraction.relations:
            record = _provenance(chunk, relation.evidence_quote)
            provenance[record.id] = record
            source = _node(
                relation.source.canonical_name,
                relation.source.entity_type,
                relation.source.aliases,
                record.id,
            )
            target = _node(
                relation.target.canonical_name,
                relation.target.entity_type,
                relation.target.aliases,
                record.id,
            )
            nodes[source.id] = _merge_node(nodes.get(source.id), source)
            nodes[target.id] = _merge_node(nodes.get(target.id), target)
            edge_id = _stable("edge", source.id, relation.relation_type, target.id)
            existing = edges.get(edge_id)
            edge = GraphEdge(
                id=edge_id,
                source_id=source.id,
                target_id=target.id,
                relation_type=relation.relation_type,
                confidence=relation.confidence,
                provenance_ids=(record.id,),
            )
            edges[edge_id] = _merge_edge(existing, edge)
            source_node = _source_node(chunk, record.id)
            nodes[source_node.id] = _merge_node(nodes.get(source_node.id), source_node)
            for entity_node in (source, target):
                support_id = _stable("edge", entity_node.id, "SUPPORTED_BY", source_node.id)
                support = GraphEdge(
                    id=support_id,
                    source_id=entity_node.id,
                    target_id=source_node.id,
                    relation_type="SUPPORTED_BY",
                    confidence=1.0,
                    provenance_ids=(record.id,),
                )
                edges[support_id] = _merge_edge(edges.get(support_id), support)
    _add_visual_associations(
        entities_by_chunk,
        edges,
        max_per_chunk=visual_max_per_chunk,
        max_degree=visual_max_degree,
    )
    return nodes, edges, provenance


def _add_visual_associations(
    entities_by_chunk: dict[str, list[GraphNode]],
    edges: dict[str, GraphEdge],
    *,
    max_per_chunk: int,
    max_degree: int,
) -> None:
    """Add a bounded presentation layer; these edges are never medical claims."""

    if max_per_chunk == 0 or max_degree == 0:
        return
    factual_pairs = {
        frozenset((edge.source_id, edge.target_id))
        for edge in edges.values()
        if not edge.visual_only and edge.relation_type != "SUPPORTED_BY"
    }
    visual_degree: dict[str, int] = {}
    for chunk_id in sorted(entities_by_chunk):
        unique_nodes = {node.id: node for node in entities_by_chunk[chunk_id]}
        values = sorted(unique_nodes.values(), key=lambda item: item.id)
        added = 0
        for index, left in enumerate(values):
            for right in values[index + 1 :]:
                if added >= max_per_chunk:
                    break
                pair = frozenset((left.id, right.id))
                if pair in factual_pairs:
                    continue
                if (
                    visual_degree.get(left.id, 0) >= max_degree
                    or visual_degree.get(right.id, 0) >= max_degree
                ):
                    continue
                edge_id = _stable("edge", left.id, "CO_MENTIONED", right.id)
                record_ids = tuple(sorted(set(left.provenance_ids) & set(right.provenance_ids)))
                if not record_ids or edge_id in edges:
                    continue
                edges[edge_id] = GraphEdge(
                    id=edge_id,
                    source_id=left.id,
                    target_id=right.id,
                    relation_type="CO_MENTIONED",
                    confidence=0.45,
                    provenance_ids=record_ids,
                    visual_only=True,
                )
                visual_degree[left.id] = visual_degree.get(left.id, 0) + 1
                visual_degree[right.id] = visual_degree.get(right.id, 0) + 1
                added += 1
            if added >= max_per_chunk:
                break


def _node(name: str, entity_type, aliases: list[str], provenance_id: str) -> GraphNode:
    return GraphNode(
        id=_stable("node", entity_type, name.casefold()),
        canonical_name=name,
        entity_type=entity_type,
        aliases=tuple(sorted(set(aliases))),
        provenance_ids=(provenance_id,),
    )


def _source_node(chunk: TextChunk, provenance_id: str) -> GraphNode:
    entity_type = "Guideline" if any(
        value in chunk.file_name for value in ("指南", "规范", "程序", "方案")
    ) else "EvidenceSource"
    doc_id = chunk.parent_doc_id or chunk.source_hash
    return GraphNode(
        id=_stable("node", entity_type, doc_id),
        canonical_name=chunk.source_title or chunk.file_name,
        entity_type=entity_type,
        aliases=(),
        provenance_ids=(provenance_id,),
    )


def _provenance(chunk: TextChunk, quote: str) -> ProvenanceRecord:
    return ProvenanceRecord(
        id=_stable("prov", chunk.id, quote),
        doc_id=chunk.parent_doc_id or chunk.source_hash,
        chunk_id=chunk.id,
        relative_path=chunk.relative_path,
        file_name=chunk.file_name,
        page=chunk.page,
        section=chunk.section,
        source_type=chunk.source_type,
        source_url=chunk.source_url,
        quote=quote,
        content_hash=chunk.content_hash or hashlib.sha256(chunk.text.encode()).hexdigest(),
        authority_level=chunk.authority_level,
    )


def _merge_node(existing: GraphNode | None, incoming: GraphNode) -> GraphNode:
    if existing is None:
        return incoming
    return replace(
        existing,
        aliases=tuple(sorted({*existing.aliases, *incoming.aliases})),
        provenance_ids=tuple(sorted({*existing.provenance_ids, *incoming.provenance_ids})),
    )


def _merge_edge(existing: GraphEdge | None, incoming: GraphEdge) -> GraphEdge:
    if existing is None:
        return incoming
    return replace(
        existing,
        confidence=max(existing.confidence, incoming.confidence),
        provenance_ids=tuple(sorted({*existing.provenance_ids, *incoming.provenance_ids})),
    )


def _stable(prefix: str, *parts: str) -> str:
    return f"{prefix}_{hashlib.sha256(chr(31).join(parts).encode()).hexdigest()[:24]}"


def _sorted(values: dict[str, Any]) -> list[Any]:
    return [values[key] for key in sorted(values)]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
