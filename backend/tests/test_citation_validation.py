import json
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.pubmed.models import PubMedArticle
from app.rag.models import RagSource
from app.schemas.chat import ChatRequest
from app.services.qwen_service import (
    CitationAuditFormatError,
    QwenService,
    QwenTimeoutError,
)
from app.services.source_quality import (
    CitationAuditResult,
    deduplicate_local_sources,
    deduplicate_pubmed_articles,
    finalize_audited_citations,
    normalize_source_url,
)


def article(pmid: str, title: str, abstract: str = "") -> PubMedArticle:
    return PubMedArticle(pmid=pmid, title=title, abstract=abstract)


def test_citation_entailment_audit_is_enabled_by_default() -> None:
    assert Settings.model_fields["citation_entailment_audit_enabled"].default is True


def chunks(document_id: str, count: int, *, file_name: str = "专家解答.pdf") -> list[RagSource]:
    return [
        RagSource(
            file_name=file_name,
            page=index + 1,
            content=f"片段 {index + 1}",
            document_id=document_id,
            source_id=f"local:{index + 1}",
        )
        for index in range(count)
    ]


def test_sci_006_four_catch_up_chunks_become_one_source() -> None:
    assert len(deduplicate_local_sources(chunks("dtap-catch-up", 4))) == 1


def test_sci_015_multiple_dtap_technical_chunks_become_one_source() -> None:
    assert (
        len(deduplicate_local_sources(chunks("dtap-technical", 3, file_name="百白破技术方案.pdf")))
        == 1
    )


def test_normalized_url_deduplicates_tracking_fragment_and_trailing_slash() -> None:
    assert (
        normalize_source_url("HTTPS://Example.COM/path/?utm_source=x&ref=y#part")
        == "https://example.com/path"
    )
    sources = [
        RagSource(
            "a.md",
            None,
            "甲",
            source_type="web",
            source_url="https://EXAMPLE.com/x/?gclid=1",
        ),
        RagSource("b.md", None, "乙", source_type="web", source_url="https://example.com/x#part"),
    ]
    assert len(deduplicate_local_sources(sources)) == 1


def test_pubmed_deduplicates_by_pmid() -> None:
    assert len(deduplicate_pubmed_articles([article("123", "A"), article("123", "B")])) == 1


def test_only_declared_existing_markers_are_visible() -> None:
    local = chunks("doc", 1)
    result = finalize_audited_citations(
        CitationAuditResult(
            "支持。[[local:1]] 无效。[[local:99]]",
            ("local:1", "local:99", "pubmed:9"),
        ),
        local,
        [],
    )
    assert result.answer == "支持。［1］ 无效。"
    assert len(result.sources) == 1


def test_same_document_markers_share_one_number_and_merged_pages() -> None:
    local = chunks("same-doc", 2)
    result = finalize_audited_citations(
        CitationAuditResult("甲。[[local:1]]乙。[[local:2]]", ("local:1", "local:2")),
        local,
        [],
    )
    assert result.answer == "甲。［1］乙。［1］"
    assert len(result.sources) == 1
    assert result.sources[0].pages == (1, 2)


def test_explicit_empty_audit_has_no_sources() -> None:
    result = finalize_audited_citations(
        CitationAuditResult("当前证据不足以确认。", ()), chunks("doc", 2), []
    )
    assert result.sources == ()


def test_duplicate_fragments_are_removed_and_summary_is_bounded() -> None:
    source = RagSource("a.pdf", 1, "相同片段", document_id="doc")
    merged = deduplicate_local_sources([source, source], max_content_chars=5)
    assert merged[0].content == "相同片段"


@pytest.mark.asyncio
async def test_invalid_audit_json_fails_closed() -> None:
    service = QwenService(Settings(_env_file=None), None)
    service._create_response = AsyncMock(return_value=("not-json", "audit-id"))
    with pytest.raises(CitationAuditFormatError):
        await service.audit_citation_entailment(
            ChatRequest(question="发热时能接种吗"),
            evidence_question="发热时能接种吗",
            answer="生病时接种会影响抗体产生。",
            local_sources=chunks("doc", 1),
            pubmed_articles=[],
        )
    assert service._create_response.await_count == 2


@pytest.mark.asyncio
async def test_audit_receives_first_pubmed_relevant_excerpt_and_original_question() -> None:
    service = QwenService(Settings(_env_file=None), None)
    service._create_response = AsyncMock(return_value=(json.dumps({
        "answer": "文献讨论的是轻微患病时的接种。[[pubmed:1]]基础科普解释。",
        "source_ids": ["pubmed:1"],
    }), "audit-id"))
    question = "我家宝宝目前是甲流，同时给他注射甲流疫苗可以吗"
    first = article(
        "1", "Vaccination during minor illness in children",
        "Background discussion. Vaccination during minor illness in children was reviewed.",
    )
    second = article("2", "Influenza illness", "Influenza vaccination during illness in children.")
    result = await service.audit_citation_entailment(
        ChatRequest(question=question, session_id="main-id"),
        evidence_question="患病期间能接种吗", answer="原回答",
        local_sources=chunks("doc", 1), pubmed_articles=[first, second],
    )
    call = service._create_response.await_args.kwargs
    data = json.loads(call["user_input"])
    assert data["question"] == question
    assert "answer" not in data
    assert "原回答" not in call["user_input"]
    assert data["evidence_question"] == "患病期间能接种吗"
    assert data["primary_pubmed_evidence"] == {
        "source_id": "pubmed:1",
        "excerpt": "Vaccination during minor illness in children was reviewed.",
    }
    assert [item["source_id"] for item in data["candidate_evidence"]] == [
        "local:1", "pubmed:1", "pubmed:2",
    ]
    assert call["store"] is False
    assert call["use_previous_response_id"] is False
    finalized = finalize_audited_citations(result, chunks("doc", 1), [first, second])
    assert finalized.answer == "文献讨论的是轻微患病时的接种。［1］基础科普解释。"
    assert finalized.sources == (first,)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_output", [
    "not-json", '{"answer":"truncated',
    '{"answer":"说明", "source_ids":"pubmed:1"}',
    '{"answer":"   ", "source_ids":[]}',
])
async def test_audit_format_retry_regenerates_with_identical_evidence(invalid_output: str) -> None:
    service = QwenService(Settings(_env_file=None), None)
    recovered = "文献讨论的是轻微患病时的接种。[[pubmed:1]]请告知医生当前病情。[[local:1]]"
    service._create_response = AsyncMock(side_effect=[
        (invalid_output, "audit-id"), (recovered, "retry-id"),
    ])
    first = article("1", "Practice review", "Vaccination during minor illness in children.")
    result = await service.audit_citation_entailment(
        ChatRequest(question="甲流期间能接种吗", session_id="main-response"),
        evidence_question="甲流期间能接种吗", answer="原回答",
        local_sources=chunks("doc", 1), pubmed_articles=[first],
    )
    assert result.answer == recovered
    assert result.source_ids == ("pubmed:1", "local:1")
    calls = service._create_response.await_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["user_input"] == calls[1].kwargs["user_input"]
    assert invalid_output not in calls[1].kwargs["user_input"]
    assert "不输出 JSON" in calls[1].kwargs["instructions"]
    for call in calls:
        assert call.kwargs["store"] is False
        assert call.kwargs["use_previous_response_id"] is False
    finalized = finalize_audited_citations(result, chunks("doc", 1), [first])
    assert finalized.answer == "文献讨论的是轻微患病时的接种。［1］请告知医生当前病情。［2］"
    assert len(finalized.sources) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_output", [
    '{"answer":"truncated', "```json\nbroken\n```", "", "not-json",
])
async def test_audit_never_displays_malformed_retry_output(retry_output: str) -> None:
    service = QwenService(Settings(_env_file=None), None)
    service._create_response = AsyncMock(side_effect=[("broken", "id"), (retry_output, "id2")])
    with pytest.raises(CitationAuditFormatError):
        await service.audit_citation_entailment(
            ChatRequest(question="接种问题"), evidence_question="接种问题", answer="原回答",
            local_sources=chunks("doc", 1), pubmed_articles=[],
        )
    assert service._create_response.await_count == 2


@pytest.mark.asyncio
async def test_audit_retry_timeout_propagates_without_additional_calls() -> None:
    service = QwenService(Settings(_env_file=None), None)
    service._create_response = AsyncMock(side_effect=[("broken", "id"), QwenTimeoutError])
    with pytest.raises(QwenTimeoutError):
        await service.audit_citation_entailment(
            ChatRequest(question="接种问题"), evidence_question="接种问题", answer="原回答",
            local_sources=chunks("doc", 1), pubmed_articles=[],
        )
    assert service._create_response.await_count == 2


@pytest.mark.asyncio
async def test_audit_accepts_natural_answer_and_derives_real_citations_on_first_call() -> None:
    service = QwenService(Settings(_env_file=None), None)
    text = "文献比较了常规接种与未接种的健康结局。[[pubmed:1]]基础术语解释。"
    service._create_response = AsyncMock(return_value=(text, "audit-id"))
    first = article(
        "1", "Vaccination outcomes", "Health outcomes of vaccination compared to no vaccination.",
    )
    result = await service.audit_citation_entailment(
        ChatRequest(question="甲流期间能接种吗"), evidence_question="甲流期间能接种吗",
        answer="未经支持的接种判断", local_sources=[], pubmed_articles=[first],
    )
    assert result.answer == text
    assert result.source_ids == ("pubmed:1",)
    service._create_response.assert_awaited_once()
    assert "原回答不作为证据传入" in service._create_response.await_args.kwargs["instructions"]


@pytest.mark.asyncio
async def test_combined_final_keeps_non_vaccine_scope_without_returning_internal_markers() -> None:
    service = QwenService(Settings(_env_file=None), None)
    service._create_response = AsyncMock(return_value=(
        "[[scope:non_vaccine]]本助手只解答疫苗知识。", "stored-final-id",
    ))
    result = await service.audit_citation_entailment(
        ChatRequest(question="红烧肉怎么做？"), evidence_question="红烧肉怎么做？", answer="",
        local_sources=chunks("doc", 1), pubmed_articles=[], as_final_answer=True,
    )
    assert result.is_vaccine_related is False
    assert result.answer == "本助手只解答疫苗知识。"
    assert result.source_ids == ()
    assert result.session_id == "stored-final-id"
    service._create_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_science_final_preserves_uncited_conservative_advice_and_topic_citation() -> None:
    from types import SimpleNamespace

    client = AsyncMock()
    client.responses.create.return_value = SimpleNamespace(
        id="science-final",
        output_text="资料讨论了流感疫苗的预防用途。[[pubmed:123]]\n宝宝当前能否接种，建议先请接种人员评估。",
    )
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    result = await service.audit_citation_entailment(
        ChatRequest(question="宝宝患甲流还能打疫苗吗", session_id="previous-final"),
        evidence_question="宝宝患甲流还能打疫苗吗", answer="",
        local_sources=[], pubmed_articles=[article("123", "Influenza vaccine", "Prevention.")],
        as_final_answer=True,
    )
    final = finalize_audited_citations(result, [], [article("123", "Influenza vaccine")])
    assert "建议先请接种人员评估" in final.answer
    assert "［1］" in final.answer
    assert len(final.sources) == 1
    call = client.responses.create.await_args.kwargs
    assert call["store"] is True
    assert call["previous_response_id"] == "previous-final"
    assert result.session_id == "science-final"
