import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.knowledge_gap.repository import JsonlKnowledgeGapRepository
from app.pubmed.models import PubMedArticle
from app.rag.models import RetrievedChunk
from app.rag.service import RetrievalResult
from app.services.evidence_assessment import EvidenceAssessmentResult
from app.services.knowledge_gap_service import KnowledgeGapService


def _retrieval() -> RetrievalResult:
    return RetrievalResult(
        chunks=[
            RetrievedChunk(
                id="chunk-1",
                file_name="本地指南.pdf",
                relative_path="本地指南.pdf",
                page=3,
                chunk_index=0,
                text="本地资料只覆盖基础安全性。",
                source_hash="hash",
                similarity=0.72,
            )
        ],
        context="<knowledge>本地资料只覆盖基础安全性。</knowledge>",
        sources=[],
    )


def _assessment(status: str = "partial") -> EvidenceAssessmentResult:
    return EvidenceAssessmentResult(
        status=status,
        reason="本地资料缺少最新研究。",
        missing_aspects=["最新研究"],
        should_search_pubmed=True,
        trigger_reason=f"assessment_{status}",
        assessment_method="hybrid",
    )


@pytest.mark.asyncio
async def test_pubmed_evidence_creates_pending_candidate_only(tmp_path: Path) -> None:
    store = tmp_path / "runtime" / "knowledge_gaps.jsonl"
    service = KnowledgeGapService(JsonlKnowledgeGapRepository(store))

    gap = await service.capture_candidate(
        original_query="请给我最新 HPV 疫苗安全性研究",
        rewritten_query="最新 HPV vaccine safety research",
        retrieval=_retrieval(),
        assessment=_assessment(),
        pubmed_articles=[
            PubMedArticle(
                pmid="12345678",
                title="HPV vaccine safety",
                abstract="External evidence.",
            )
        ],
    )

    assert gap is not None
    assert gap.status == "pending"
    assert gap.pubmed_pmids == ["12345678"]
    assert gap.candidate_claims == []
    record = json.loads(store.read_text(encoding="utf-8").strip())
    assert record["status"] == "pending"
    assert record["reviewed_at"] is None
    assert record["pubmed_pmids"] == ["12345678"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["insufficient", "conflict"])
async def test_critical_gap_is_recorded_even_when_pubmed_returns_empty(
    status: str,
) -> None:
    repository = AsyncMock()
    repository.create.side_effect = lambda gap: gap
    service = KnowledgeGapService(repository)

    gap = await service.capture_candidate(
        original_query="内部未覆盖的问题",
        rewritten_query="内部未覆盖的问题",
        retrieval=RetrievalResult(chunks=[], context="", sources=[]),
        assessment=_assessment(status),
        pubmed_articles=[],
    )

    assert gap is not None
    assert gap.assessment_status == status
    assert gap.pubmed_pmids == []
    assert gap.status == "pending"


@pytest.mark.asyncio
async def test_partial_without_external_candidate_is_not_persisted() -> None:
    repository = AsyncMock()
    service = KnowledgeGapService(repository)

    gap = await service.capture_candidate(
        original_query="本地覆盖不完整",
        rewritten_query="本地覆盖不完整",
        retrieval=_retrieval(),
        assessment=_assessment("partial"),
        pubmed_articles=[],
    )

    assert gap is None
    repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_sufficient_evidence_never_creates_candidate() -> None:
    repository = AsyncMock()
    service = KnowledgeGapService(repository)
    assessment = EvidenceAssessmentResult(
        status="sufficient",
        reason="本地证据完整。",
        missing_aspects=[],
        should_search_pubmed=False,
        trigger_reason=None,
        assessment_method="hybrid",
    )

    gap = await service.capture_candidate(
        original_query="基础疫苗问题",
        rewritten_query="基础疫苗问题",
        retrieval=_retrieval(),
        assessment=assessment,
        pubmed_articles=[],
    )

    assert gap is None
    repository.create.assert_not_awaited()
