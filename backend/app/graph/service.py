from __future__ import annotations

import html
import json
import re
import threading
from hashlib import sha256
from pathlib import Path

from app.core.config import Settings
from app.graph.models import GraphPath, GraphRetrievalResult
from app.graph.snapshot import graph_version_directory, validate_snapshot
from app.graph.storage import JsonGraphStore
from app.graph.validation import validate_graph_artifacts
from app.graph.vocabulary import RELATION_LABELS
from app.rag.index_versions import read_active_pointer, resolve_active_index, version_directory
from app.rag.models import RagSource

_GRAPH_INTENT = re.compile(r"为什么|为何|如何|怎么|机制|导致|关系|作用|影响|产生|形成|进展")


class GraphService:
    def __init__(
        self,
        settings: Settings,
        *,
        index_path_override: Path | None = None,
        index_version_override: str | None = None,
    ) -> None:
        self._settings = settings
        self._index_path_override = index_path_override
        self._index_version_override = index_version_override
        self._active_path: Path | None = None
        self._active_version: str | None = None
        self._store: JsonGraphStore | None = None
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> GraphService:
        return cls(settings)

    @classmethod
    def for_index_version(cls, settings: Settings, index_version: str) -> GraphService:
        return cls(
            settings,
            index_path_override=version_directory(settings.rag_index_dir, index_version),
            index_version_override=index_version,
        )

    def retrieve(self, query: str) -> GraphRetrievalResult:
        if not self._settings.graph_rag_enabled:
            return GraphRetrievalResult(trace={"status": "disabled"})
        store = self._ensure_store()
        seeds = self._link_entities(query, store)
        if not seeds or not _GRAPH_INTENT.search(query):
            return GraphRetrievalResult(
                trace={"status": "not_applicable", "linked_entities": len(seeds)}
            )
        paths = self._traverse(store, seeds)
        selected = paths[: self._settings.graph_max_paths]
        context = _render_context(selected, self._settings.graph_context_max_chars)
        sources = _sources(selected)
        return GraphRetrievalResult(
            paths=selected,
            context=context,
            sources=sources,
            trace={
                "status": "retrieved",
                "linked_entities": [store.nodes[item].canonical_name for item in seeds],
                "candidate_paths": len(paths),
                "selected_paths": len(selected),
                "max_hops": self._settings.graph_max_hops,
            },
        )

    def _ensure_store(self) -> JsonGraphStore:
        graph_dir: Path | None = None
        if self._index_path_override is not None and self._index_version_override is not None:
            path, version = self._index_path_override, self._index_version_override
        else:
            path, version = resolve_active_index(self._settings.rag_index_dir)
            pointer = read_active_pointer(self._settings.rag_index_dir)
            graph_version = pointer.get("graph_version")
            if graph_version:
                graph_path = graph_version_directory(
                    self._settings.graph_snapshot_dir,
                    graph_version,
                )
                validate_snapshot(graph_path, index_version=version)
                graph_dir = graph_path
        cache_path = graph_dir or path
        if (
            self._store is not None
            and cache_path == self._active_path
            and version == self._active_version
        ):
            return self._store
        with self._lock:
            if (
                self._store is None
                or cache_path != self._active_path
                or version != self._active_version
            ):
                if graph_dir is not None:
                    self._store = JsonGraphStore(
                        graph_dir,
                        expected_index_version=version,
                    )
                else:
                    self._validate_runtime_graph(path, version)
                    self._store = JsonGraphStore(path / "graph", expected_index_version=version)
                self._active_path = cache_path
                self._active_version = version
        return self._store

    def _validate_runtime_graph(self, index_path: Path, index_version: str) -> None:
        graph_dir = index_path / "graph"
        validate_graph_artifacts(
            graph_dir,
            index_version=index_version,
            chunk_catalog_path=index_path / "chunks.jsonl",
        )
        index_manifest = json.loads(
            (index_path / "manifest.json").read_text(encoding="utf-8")
        )
        graph_manifest = json.loads(
            (graph_dir / "manifest.json").read_text(encoding="utf-8")
        )
        graph_binding = index_manifest.get("graph") or {}
        if graph_manifest.get("schema_version") != self._settings.graph_schema_version:
            raise ValueError("configured graph schema version mismatch")
        if (
            graph_manifest.get("extraction_rules_version")
            != self._settings.graph_extraction_rules_version
        ):
            raise ValueError("configured graph extraction rules version mismatch")
        actual_manifest_hash = sha256((graph_dir / "manifest.json").read_bytes()).hexdigest()
        if graph_binding.get("manifest_sha256") != actual_manifest_hash:
            raise ValueError("graph manifest hash mismatch")

    @staticmethod
    def _link_entities(query: str, store: JsonGraphStore) -> list[str]:
        normalized = _normalize(query)
        candidates: list[tuple[int, str]] = []
        for node in store.nodes.values():
            aliases = {*node.aliases, node.canonical_name}
            best = max(
                (len(_normalize(alias)) for alias in aliases if _normalize(alias) in normalized),
                default=0,
            )
            if best:
                candidates.append((best, node.id))
        return [node_id for _, node_id in sorted(candidates, key=lambda item: (-item[0], item[1]))]

    def _traverse(self, store: JsonGraphStore, seeds: list[str]) -> list[GraphPath]:
        adjacency: dict[str, list] = {node_id: [] for node_id in store.nodes}
        for edge in store.edges.values():
            if (
                not edge.provenance_ids
                or edge.relation_type == "SUPPORTED_BY"
                or edge.visual_only
            ):
                continue
            adjacency.setdefault(edge.source_id, []).append(edge)
            adjacency.setdefault(edge.target_id, []).append(edge)
        paths: dict[tuple[str, ...], GraphPath] = {}
        seed_set = set(seeds)
        for seed in seeds:
            queue: list[tuple[list[str], list]] = [([seed], [])]
            while queue:
                node_ids, edge_path = queue.pop(0)
                if edge_path:
                    path = _make_path(store, seed_set, node_ids, edge_path)
                    paths.setdefault(tuple(edge.id for edge in edge_path), path)
                if len(edge_path) >= self._settings.graph_max_hops:
                    continue
                current = node_ids[-1]
                for edge in sorted(adjacency.get(current, []), key=lambda item: item.id):
                    next_node = edge.target_id if edge.source_id == current else edge.source_id
                    if next_node in node_ids:
                        continue
                    queue.append(([*node_ids, next_node], [*edge_path, edge]))
        return sorted(
            paths.values(),
            key=lambda item: (-item.score, len(item.edges), item.edges[0].id),
        )


def _make_path(store, seed_set, node_ids, edges) -> GraphPath:
    provenance_ids = {item for edge in edges for item in edge.provenance_ids}
    provenance = tuple(
        sorted(
            (store.provenance[item] for item in provenance_ids if item in store.provenance),
            key=lambda item: (-item.authority_level, item.id),
        )
    )
    seed_coverage = len(seed_set.intersection(node_ids))
    confidence = sum(edge.confidence for edge in edges) / len(edges)
    authority = max((item.authority_level for item in provenance), default=0)
    score = seed_coverage * 2.0 + confidence + authority * 0.05 - (len(edges) - 1) * 0.2
    return GraphPath(
        seed_entities=tuple(
            store.nodes[item].canonical_name for item in node_ids if item in seed_set
        ),
        nodes=tuple(store.nodes[item] for item in node_ids),
        edges=tuple(edges),
        provenance=provenance,
        score=score,
    )


def _render_context(paths: list[GraphPath], budget: int) -> str:
    blocks: list[str] = []
    used = 0
    for index, path in enumerate(paths, start=1):
        chain_parts: list[str] = []
        for edge in path.edges:
            source = next(node for node in path.nodes if node.id == edge.source_id)
            target = next(node for node in path.nodes if node.id == edge.target_id)
            chain_parts.append(
                f"{source.canonical_name} --{RELATION_LABELS[edge.relation_type]}--> "
                f"{target.canonical_name}"
            )
        evidence = path.provenance[0] if path.provenance else None
        if evidence is None:
            continue
        location = f" page=\"{evidence.page}\"" if evidence.page is not None else ""
        section = (
            f" section=\"{html.escape(evidence.section, quote=True)}\""
            if evidence.section
            else ""
        )
        block = (
            f'<graph_knowledge path="{index}" file="{html.escape(evidence.file_name, quote=True)}"'
            f'{location}{section} chunk_id="{html.escape(evidence.chunk_id, quote=True)}">\n'
            f"关系路径：{'；'.join(html.escape(item) for item in chain_parts)}\n"
            f"证据摘录：{html.escape(evidence.quote)}\n"
            "</graph_knowledge>"
        )
        if used + len(block) > budget:
            break
        blocks.append(block)
        used += len(block)
    return "\n".join(blocks)


def _sources(paths: list[GraphPath]) -> list[RagSource]:
    sources: list[RagSource] = []
    seen: set[tuple[str, int | None, str | None, str]] = set()
    for path in paths:
        for item in path.provenance:
            key = (item.relative_path, item.page, item.section, item.quote)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                RagSource(
                    file_name=item.file_name,
                    page=item.page,
                    content=item.quote,
                    source_type=item.source_type,
                    source_url=item.source_url,
                    section=item.section,
                )
            )
    return sources


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()
