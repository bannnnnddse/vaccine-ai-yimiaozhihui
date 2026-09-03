from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

KnowledgeGapStatus = Literal[
    "pending",
    "in_review",
    "approved",
    "publishing",
    "rejected",
    "hold",
    "published",
]


class InternalEvidenceSnapshot(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    page: int | None = Field(default=None, ge=1)
    source_type: str | None = Field(default=None, max_length=30)
    source_url: str | None = Field(default=None, max_length=2048)
    similarity: float = Field(ge=0, le=1)
    excerpt: str = Field(min_length=1, max_length=1200)
    relative_path: str | None = Field(default=None, max_length=500)
    source_title: str | None = Field(default=None, max_length=300)
    section: str | None = Field(default=None, max_length=300)


class PubMedEvidenceSnapshot(BaseModel):
    pmid: str = Field(pattern=r"^\d{1,10}$")
    title: str = Field(min_length=1, max_length=1000)
    abstract_excerpt: str = Field(default="", max_length=2000)
    journal: str = Field(default="", max_length=500)
    year: int | None = Field(default=None, ge=1800, le=2200)
    doi: str | None = Field(default=None, max_length=500)
    url: str = Field(max_length=2048)


class CandidateClaim(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    evidence_pmids: list[str] = Field(min_length=1, max_length=20)


class KnowledgeGap(BaseModel):
    """A captured evidence gap with an explicit human review lifecycle."""

    id: str = Field(min_length=1, max_length=64)
    original_query: str = Field(min_length=1, max_length=1000)
    rewritten_query: str = Field(min_length=1, max_length=2000)
    internal_evidence: list[InternalEvidenceSnapshot] = Field(
        default_factory=list,
        max_length=10,
    )
    assessment_status: Literal["partial", "insufficient", "conflict"]
    assessment_reason: str = Field(min_length=1, max_length=1000)
    missing_aspects: list[str] = Field(default_factory=list, max_length=10)
    pubmed_pmids: list[str] = Field(default_factory=list, max_length=20)
    pubmed_evidence: list[PubMedEvidenceSnapshot] = Field(default_factory=list, max_length=20)
    candidate_claims: list[CandidateClaim] = Field(default_factory=list, max_length=20)
    trigger_reason: str = Field(min_length=1, max_length=300)
    status: KnowledgeGapStatus = "pending"
    reviewer_note: str | None = Field(default=None, max_length=4000)
    created_at: datetime
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    version: int = Field(default=1, ge=1)
    draft_file_name: str | None = Field(default=None, max_length=255)
    draft_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    draft_generated_at: datetime | None = None
    published_relative_path: str | None = Field(default=None, max_length=500)


class KnowledgeGapAuditEvent(BaseModel):
    id: int
    gap_id: str
    event_type: str
    actor: str
    details: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
