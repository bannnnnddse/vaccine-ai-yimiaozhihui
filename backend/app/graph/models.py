from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.rag.models import RagSource

EntityType = Literal[
    "Vaccine",
    "Disease",
    "Pathogen",
    "Population",
    "AdverseEvent",
    "ImmuneEntity",
    "Schedule",
    "EvidenceSource",
    "Guideline",
]

RelationType = Literal[
    "PREVENTS",
    "CAUSES",
    "CAN_PROGRESS_TO",
    "INDICATED_FOR",
    "HAS_SCHEDULE",
    "HAS_CONTRAINDICATION",
    "ACTIVATES",
    "PRODUCES",
    "NEUTRALIZES",
    "INCREASES_RISK",
    "DECREASES_RISK",
    "IS_A",
    "PART_OF",
    "SUPPORTED_BY",
    "CO_MENTIONED",
]


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    canonical_name: str
    entity_type: EntityType
    aliases: tuple[str, ...] = ()
    provenance_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    confidence: float
    provenance_ids: tuple[str, ...]
    visual_only: bool = False


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    id: str
    doc_id: str
    chunk_id: str
    relative_path: str
    file_name: str
    page: int | None
    section: str | None
    source_type: str
    source_url: str | None
    quote: str
    content_hash: str
    authority_level: int = 0


@dataclass(frozen=True, slots=True)
class GraphPath:
    seed_entities: tuple[str, ...]
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    provenance: tuple[ProvenanceRecord, ...]
    score: float


@dataclass(frozen=True, slots=True)
class GraphRetrievalResult:
    paths: list[GraphPath] = field(default_factory=list)
    context: str = ""
    sources: list[RagSource] = field(default_factory=list)
    trace: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EntityDefinition:
    canonical_name: str
    entity_type: EntityType
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EntityMention:
    definition: EntityDefinition
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ExtractedRelation:
    source: EntityDefinition
    target: EntityDefinition
    relation_type: RelationType
    confidence: float
    quote: str
