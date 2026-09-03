from __future__ import annotations

from typing import Any, Protocol


class SemanticaUnavailableError(RuntimeError):
    pass


class GraphBuilderLike(Protocol):
    def build(self, sources: Any, **options: Any) -> dict[str, Any]: ...


class SemanticaGraphBuilderAdapter:
    """Uses Semantica only after project-owned medical validation has completed."""

    def __init__(self, builder: GraphBuilderLike | None = None) -> None:
        if builder is None:
            try:
                from semantica.kg import GraphBuilder
            except ImportError as exc:
                raise SemanticaUnavailableError(
                    "Semantica is required in the isolated graph worker environment"
                ) from exc
            builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)
        self._builder = builder

    def build(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> dict[str, Any]:
        graph = self._builder.build(
            {"entities": entities, "relationships": relationships},
            extract=False,
            extract_relations=False,
            extract_triplets=False,
        )
        output_entities = graph.get("entities")
        output_relationships = graph.get("relationships")
        if not isinstance(output_entities, list) or not isinstance(output_relationships, list):
            raise ValueError("Semantica graph output is incomplete")
        expected_nodes = {str(item["id"]) for item in entities}
        actual_nodes = {str(item.get("id")) for item in output_entities}
        if expected_nodes != actual_nodes:
            raise ValueError("Semantica changed or dropped validated graph nodes")
        expected_edges = {
            (str(item["source"]), str(item["target"]), str(item["type"]))
            for item in relationships
        }
        actual_edges = {
            (str(item.get("source")), str(item.get("target")), str(item.get("type")))
            for item in output_relationships
        }
        if expected_edges != actual_edges:
            raise ValueError("Semantica changed or dropped validated graph relationships")
        return graph
