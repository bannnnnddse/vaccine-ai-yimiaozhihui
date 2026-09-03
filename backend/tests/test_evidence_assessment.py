from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.rag.models import RetrievedChunk
from app.rag.service import RetrievalResult
from app.services.evidence_assessment import (
    EvidenceAssessmentService,
    EvidenceSemanticAssessment,
)


def _retrieval(*chunks: RetrievedChunk) -> RetrievalResult:
    return RetrievalResult(chunks=list(chunks), context="context", sources=[])


def _chunk(text: str, similarity: float = 0.82, chunk_id: str = "chunk-1") -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        file_name="指南.pdf",
        relative_path="指南.pdf",
        page=1,
        chunk_index=0,
        text=text,
        source_hash="hash",
        similarity=similarity,
    )


@pytest.mark.asyncio
async def test_no_hit_is_insufficient_without_calling_llm() -> None:
    assessor = AsyncMock()
    result = await EvidenceAssessmentService(assessor).assess("HPV 疫苗安全吗？", _retrieval())

    assert result.status == "insufficient"
    assert result.should_search_pubmed is True
    assert result.assessment_method == "rule"
    assessor.assess_local_evidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_semantically_strong_top_k_is_sufficient() -> None:
    assessor = AsyncMock()
    assessor.assess_local_evidence.return_value = EvidenceSemanticAssessment(
        status="sufficient",
        reason="多条本地证据共同覆盖安全性结论和常见反应。",
        missing_aspects=[],
    )
    retrieval = _retrieval(
        _chunk("HPV 疫苗安全性监测结论。", chunk_id="one"),
        _chunk("常见接种反应和处理边界。", 0.78, "two"),
    )

    result = await EvidenceAssessmentService(assessor).assess("HPV 疫苗安全吗？", retrieval)

    assert result.status == "sufficient"
    assert result.should_search_pubmed is False
    assert result.assessment_method == "hybrid"
    called_retrieval = assessor.assess_local_evidence.await_args.args[1]
    assert len(called_retrieval.chunks) == 2


@pytest.mark.asyncio
async def test_clear_high_confidence_top_k_skips_semantic_assessment() -> None:
    assessor = AsyncMock()
    retrieval = _retrieval(
        replace(_chunk("HPV 疫苗安全性监测结论。", chunk_id="one"), relevance_score=0.95),
        replace(
            _chunk("HPV 疫苗常见接种反应。", chunk_id="two"),
            relevance_score=0.85,
        ),
    )

    result = await EvidenceAssessmentService(assessor).assess("HPV 疫苗安全吗？", retrieval)

    assert result.status == "sufficient"
    assert result.should_search_pubmed is False
    assert result.trigger_reason == "high_confidence_local_evidence"
    assert result.assessment_method == "rule"
    assessor.assess_local_evidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_complex_question_keeps_semantic_assessment_despite_high_scores() -> None:
    assessor = AsyncMock()
    assessor.assess_local_evidence.return_value = EvidenceSemanticAssessment(
        status="partial",
        reason="机制证据充分，但持续时间证据不足。",
        missing_aspects=["保护持续时间"],
    )
    retrieval = _retrieval(
        replace(_chunk("疫苗诱导免疫记忆。", chunk_id="one"), relevance_score=0.98),
        replace(_chunk("形成保护性抗体。", chunk_id="two"), relevance_score=0.93),
    )

    result = await EvidenceAssessmentService(assessor).assess(
        "疫苗如何产生保护，能持续多久？",
        retrieval,
    )

    assert result.status == "partial"
    assert result.assessment_method == "hybrid"
    assessor.assess_local_evidence.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_named_pathogen_or_product_forces_pubmed_before_semantic_assessment() -> None:
    assessor = AsyncMock()
    assessor.assess_local_evidence.return_value = EvidenceSemanticAssessment(
        status="sufficient",
        reason="泛化不良反应材料看似足够。",
        missing_aspects=[],
    )
    retrieval = _retrieval(
        _chunk("接种后出现严重疑似预防接种异常反应时，应及时就医。")
    )

    result = await EvidenceAssessmentService(assessor).assess(
        "既往可能感染 Coxiella burnetii 的成年人接种 Q-VAX 前，"
        "是否需要血清学检测和皮肤试验？",
        retrieval,
    )

    assert result.status == "partial"
    assert result.should_search_pubmed is True
    assert result.trigger_reason == "missing_required_identifiers"
    assert result.missing_aspects == [
        "关键标识符“Coxiella burnetii”的专门证据",
        "关键标识符“Q-VAX”的专门证据",
    ]
    assessor.assess_local_evidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_mixed_case_product_identifier_must_exist_in_local_evidence() -> None:
    assessor = AsyncMock()
    retrieval = _retrieval(
        replace(_chunk("COVID-19 加强针免疫持久性研究。"), relevance_score=0.99),
        replace(_chunk("异源接种的一般研究资料。", chunk_id="two"), relevance_score=0.98),
    )

    result = await EvidenceAssessmentService(assessor).assess(
        "Com-COV2 异源接种结果是什么？",
        retrieval,
    )

    assert result.status == "partial"
    assert result.trigger_reason == "missing_required_identifiers"
    assert result.missing_aspects == ["关键标识符“Com-COV2”的专门证据"]
    assessor.assess_local_evidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_semantic_assessor_can_mark_partial_evidence() -> None:
    assessor = AsyncMock()
    assessor.assess_local_evidence.return_value = EvidenceSemanticAssessment(
        status="partial",
        reason="证据说明了免疫原理，但没有覆盖保护持续时间。",
        missing_aspects=["保护持续时间"],
    )

    result = await EvidenceAssessmentService(assessor).assess(
        "疫苗如何产生保护，能持续多久？",
        _retrieval(_chunk("疫苗诱导免疫记忆。")),
    )

    assert result.status == "partial"
    assert result.should_search_pubmed is True
    assert result.trigger_reason == "assessment_partial"


@pytest.mark.asyncio
async def test_explicit_latest_research_request_forces_pubmed_by_rule() -> None:
    assessor = AsyncMock()
    result = await EvidenceAssessmentService(assessor).assess(
        "请给我最新 HPV 疫苗安全性研究和 PubMed PMID",
        _retrieval(_chunk("本地指南包含 HPV 疫苗安全性资料。")),
    )

    assert result.status == "partial"
    assert result.should_search_pubmed is True
    assert result.trigger_reason == "explicit_external_evidence_request"
    assessor.assess_local_evidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_llm_schema_falls_back_conservatively() -> None:
    assessor = AsyncMock()
    assessor.assess_local_evidence.side_effect = ValueError("invalid schema")

    result = await EvidenceAssessmentService(assessor).assess(
        "HPV 疫苗安全吗？",
        _retrieval(_chunk("相关证据。")),
    )

    assert result.status == "partial"
    assert result.should_search_pubmed is True
    assert result.trigger_reason == "semantic_assessment_failed"
