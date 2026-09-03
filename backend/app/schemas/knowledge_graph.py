from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeGraphMetaResponse(BaseModel):
    version: str
    knowledge_base_version: str
    updated_at: str
    source_documents: int
    node_count: int
    edge_count: int
    schema_version: str
    model: str


class KnowledgeGraphNode(BaseModel):
    id: str
    label: str
    type: str
    aliases: list[str] = Field(default_factory=list)
    degree: int
    source_count: int


class KnowledgeGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    relation_label: str
    confidence: float
    source_count: int
    visual_only: bool = False


class KnowledgeGraphResponse(BaseModel):
    version: str
    knowledge_base_version: str
    center_id: str | None
    depth: int
    truncated: bool
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]


class KnowledgeGraphSearchItem(BaseModel):
    id: str
    label: str
    type: str
    matched_alias: str | None = None


class KnowledgeGraphSearchResponse(BaseModel):
    version: str
    items: list[KnowledgeGraphSearchItem]


class KnowledgeGraphSource(BaseModel):
    file_name: str
    page: int | None
    section: str | None
    source_type: str
    source_url: str | None
    quote: str
    chunk_id: str


class KnowledgeGraphRelationGroup(BaseModel):
    relation: str
    relation_label: str
    neighbors: list[KnowledgeGraphNode]


class KnowledgeGraphNodeDetailResponse(BaseModel):
    version: str
    knowledge_base_version: str
    node: KnowledgeGraphNode
    relations: list[KnowledgeGraphRelationGroup]
    sources: list[KnowledgeGraphSource]
