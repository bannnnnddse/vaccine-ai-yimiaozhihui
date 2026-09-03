from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.knowledge_gap.models import CandidateClaim, KnowledgeGap, KnowledgeGapAuditEvent


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


class AdminSessionResponse(BaseModel):
    username: str
    csrf_token: str
    expires_at: int


class ReviewUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    reviewer_note: str = Field(default="", max_length=4000)
    candidate_claims: list[CandidateClaim] = Field(default_factory=list, max_length=20)


class DecisionRequest(BaseModel):
    version: int = Field(ge=1)
    reviewer_note: str = Field(min_length=1, max_length=4000)

    @field_validator("reviewer_note")
    @classmethod
    def strip_note(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reviewer note cannot be blank")
        return value.strip()


class ApproveRequest(ReviewUpdateRequest):
    title: str = Field(min_length=1, max_length=300)

    @field_validator("title", "reviewer_note")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("approval fields cannot be blank")
        return value.strip()


class PublishRequest(BaseModel):
    version: int = Field(ge=1)


class GraphRebuildRequest(BaseModel):
    mode: Literal["incremental", "full"] = "incremental"
    force_reextract: bool = False


class GraphJobResponse(BaseModel):
    task_id: str
    status: str
    kind: str
    stage: str
    progress: float
    processed_chunks: int
    total_chunks: int
    result_graph_version: str | None = None
    result_index_version: str | None = None
    error: str | None = None


class KnowledgeGapDetailResponse(BaseModel):
    gap: KnowledgeGap
    audit_events: list[KnowledgeGapAuditEvent]


class KnowledgeGapListResponse(BaseModel):
    items: list[KnowledgeGap]
    total: int
    limit: int
    offset: int


class DraftResponse(BaseModel):
    content: str
    sha256: str
    generated_at: datetime


KnowledgeGapFilterStatus = Literal[
    "pending", "in_review", "hold", "approved", "publishing", "rejected", "published"
]
