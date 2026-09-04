import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings as AppSettings
from app.pubmed.models import PubMedArticle
from app.pubmed.provider import PubMedProvider, PubMedUnavailableError
from app.rag.service import RetrievalResult
from app.schemas.chat import ChatRequest
from app.services.evidence_assessment import EvidenceAssessmentResult
from app.services.qwen_service import (
    PubMedEmptyEvidenceFinalizationError,
    QwenService,
    _broaden_zero_result_query,
)


def Settings(**kwargs: object) -> AppSettings:
    kwargs.setdefault("citation_entailment_audit_enabled", False)
    return AppSettings(**kwargs)


class FakePubMedProvider(PubMedProvider):
    def __init__(self) -> None:
        super().__init__(max_results=5)
        self.search_calls: list[tuple[str, int]] = []
        self.fetch_calls: list[list[str]] = []

    async def _search_articles(self, query: str, *, max_results: int) -> list[PubMedArticle]:
        self.search_calls.append((query, max_results))
        return [PubMedArticle(pmid="123", title="Search candidate")]

    async def _fetch_articles(self, pmids: list[str]) -> list[PubMedArticle]:
        self.fetch_calls.append(pmids)
        return [
            PubMedArticle(
                pmid=pmid,
                title="Fetched vaccine study",
                abstract="External abstract evidence.",
                journal="Vaccine",
                publication_year=2025,
            )
            for pmid in pmids
        ]


def _tool_response(
    response_id: str,
    *,
    name: str,
    arguments: dict[str, object],
    call_id: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=response_id,
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                name=name,
                arguments=json.dumps(arguments),
                call_id=call_id,
            )
        ],
    )


def _final_response(response_id: str = "final-response") -> SimpleNamespace:
    return SimpleNamespace(
        id=response_id,
        output_text=json.dumps(
            {"is_vaccine_related": True, "answer": "融合本地与 PubMed 证据的回答。"},
            ensure_ascii=False,
        ),
        output=[SimpleNamespace(type="message")],
    )


def _assessment() -> EvidenceAssessmentResult:
    return EvidenceAssessmentResult(
        status="partial",
        reason="缺少最新研究。",
        missing_aspects=["最新研究"],
        should_search_pubmed=True,
        trigger_reason="assessment_partial",
        assessment_method="hybrid",
    )


@pytest.mark.asyncio
async def test_model_search_call_is_executed_and_returned_for_final_answer() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _tool_response(
            "tool-response",
            name="pubmed_search",
            arguments={"query": "HPV vaccine safety", "max_results": 3},
            call_id="call-search",
        ),
        _final_response(),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    provider = FakePubMedProvider()

    result = await service.answer_with_pubmed_tools(
        ChatRequest(question="最新 HPV 疫苗安全性研究", session_id="prior-response"),
        RetrievalResult(chunks=[], context="<knowledge>本地资料</knowledge>", sources=[]),
        _assessment(),
        provider,
        rewritten_query="最新 HPV 疫苗安全性研究",
        max_tool_rounds=2,
    )

    assert result.analysis.answer == "融合本地与 PubMed 证据的回答。"
    assert result.analysis.session_id == "final-response"
    assert [article.pmid for article in result.articles] == ["123"]
    assert result.tool_rounds == 1
    assert provider.search_calls == [("HPV vaccine safety", 3)]
    assert provider.fetch_calls == [["123"]]

    first_call, second_call = client.responses.create.await_args_list
    assert first_call.kwargs["tool_choice"] == "required"
    assert first_call.kwargs["previous_response_id"] == "prior-response"
    assert [tool["name"] for tool in first_call.kwargs["tools"]] == ["pubmed_search"]
    assert "Automatic Term Mapping" in first_call.kwargs["instructions"]
    assert "不要臆造 MeSH" in first_call.kwargs["instructions"]
    assert second_call.kwargs["previous_response_id"] == "tool-response"
    assert second_call.kwargs["input"][0]["type"] == "function_call_output"
    assert second_call.kwargs["input"][0]["call_id"] == "call-search"
    tool_output = json.loads(second_call.kwargs["input"][0]["output"])
    assert tool_output["ok"] is True
    assert tool_output["articles"][0]["abstract"] == "External abstract evidence."


@pytest.mark.asyncio
async def test_first_successful_search_finalizes_without_a_second_tool_round() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _tool_response(
            "round-1",
            name="pubmed_search",
            arguments={"query": "vaccine evidence", "max_results": 1},
            call_id="call-1",
        ),
        _final_response("forced-final"),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    provider = FakePubMedProvider()

    result = await service.answer_with_pubmed_tools(
        ChatRequest(question="需要 PubMed 文献"),
        RetrievalResult(chunks=[], context="", sources=[]),
        _assessment(),
        provider,
        rewritten_query="需要 PubMed 文献",
        max_tool_rounds=2,
    )

    assert result.tool_rounds == 1
    assert provider.search_calls == [("vaccine evidence", 1)]
    assert provider.fetch_calls == [["123"]]
    assert client.responses.create.await_count == 2
    forced_call = client.responses.create.await_args_list[1].kwargs
    assert forced_call["tools"] == []
    assert forced_call["tool_choice"] == "none"
    assert forced_call["previous_response_id"] == "round-1"
    assert result.analysis.session_id == "forced-final"


@pytest.mark.asyncio
async def test_invalid_arguments_are_returned_without_calling_provider() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _tool_response(
            "tool-response",
            name="pubmed_search",
            arguments={"query": "", "max_results": 99},
            call_id="bad-call",
        ),
        _final_response(),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    provider = FakePubMedProvider()

    await service.answer_with_pubmed_tools(
        ChatRequest(question="文献"),
        RetrievalResult(chunks=[], context="", sources=[]),
        _assessment(),
        provider,
        rewritten_query="文献",
    )

    assert provider.search_calls == []
    output = json.loads(client.responses.create.await_args_list[1].kwargs["input"][0]["output"])
    assert output == {"ok": False, "error": "invalid_arguments"}


@pytest.mark.asyncio
async def test_empty_search_is_returned_to_model_without_fabricated_sources() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _tool_response(
            "tool-response",
            name="pubmed_search",
            arguments={"query": "novel vaccine no results", "max_results": 3},
            call_id="empty-call",
        ),
        _final_response(),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    provider = FakePubMedProvider()
    provider._search_articles = AsyncMock(return_value=[])

    result = await service.answer_with_pubmed_tools(
        ChatRequest(question="请查找一个没有结果的新疫苗"),
        RetrievalResult(chunks=[], context="", sources=[]),
        _assessment(),
        provider,
        rewritten_query="请查找一个没有结果的新疫苗",
    )

    output = json.loads(client.responses.create.await_args_list[1].kwargs["input"][0]["output"])
    assert output == {
        "ok": True,
        "articles": [],
        "search_trace": [
            {
                "attempt": "primary",
                "query": "novel vaccine no results",
                "hit_count": 0,
                "provider": "fake",
            }
        ],
    }
    assert result.articles == []


@pytest.mark.asyncio
async def test_invalid_forced_final_after_empty_searches_has_distinct_error() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _tool_response(
            "round-1",
            name="pubmed_search",
            arguments={"query": "novel vaccine no results", "max_results": 3},
            call_id="empty-call-1",
        ),
        _tool_response(
            "round-2",
            name="pubmed_search",
            arguments={"query": "novel vaccine no results", "max_results": 3},
            call_id="empty-call-2",
        ),
        SimpleNamespace(
            id="invalid-final",
            output_text="not valid JSON",
            output=[SimpleNamespace(type="message")],
        ),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    provider = FakePubMedProvider()
    provider._search_articles = AsyncMock(return_value=[])

    with pytest.raises(PubMedEmptyEvidenceFinalizationError) as raised:
        await service.answer_with_pubmed_tools(
            ChatRequest(question="请查找一个没有结果的新疫苗"),
            RetrievalResult(chunks=[], context="", sources=[]),
            _assessment(),
            provider,
            rewritten_query="请查找一个没有结果的新疫苗",
        )

    assert isinstance(raised.value.__cause__, json.JSONDecodeError)
    assert client.responses.create.await_count == 3


@pytest.mark.asyncio
async def test_invalid_early_final_is_retried_as_tool_free_json_final() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _tool_response(
            "tool-response",
            name="pubmed_search",
            arguments={"query": "influenza vaccine mechanism", "max_results": 3},
            call_id="call-search",
        ),
        SimpleNamespace(
            id="invalid-early-final",
            output_text='{"is_vaccine_related": true, "answer":',
            output=[SimpleNamespace(type="message")],
        ),
        _final_response("retried-final"),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)

    result = await service.answer_with_pubmed_tools(
        ChatRequest(question="流感疫苗如何产生保护？"),
        RetrievalResult(chunks=[], context="", sources=[]),
        _assessment(),
        FakePubMedProvider(),
        rewritten_query="流感疫苗保护机制",
    )

    assert result.analysis.session_id == "retried-final"
    assert [article.pmid for article in result.articles] == ["123"]
    assert client.responses.create.await_count == 3
    retry_call = client.responses.create.await_args_list[2].kwargs
    assert retry_call["tools"] == []
    assert retry_call["tool_choice"] == "none"
    assert retry_call["previous_response_id"] == "invalid-early-final"


@pytest.mark.asyncio
async def test_non_json_early_final_with_articles_is_used_with_sources() -> None:
    client = AsyncMock()
    prose_final = SimpleNamespace(
        id="invalid-final",
        output_text="这是根据本轮 PubMed 文献整理的科普回答。",
        output=[SimpleNamespace(type="message")],
    )
    client.responses.create.side_effect = [
        _tool_response(
            "tool-response",
            name="pubmed_search",
            arguments={"query": "influenza vaccine mechanism", "max_results": 3},
            call_id="call-search",
        ),
        prose_final,
        prose_final,
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)

    result = await service.answer_with_pubmed_tools(
        ChatRequest(question="流感疫苗如何产生保护？"),
        RetrievalResult(chunks=[], context="", sources=[]),
        _assessment(),
        FakePubMedProvider(),
        rewritten_query="流感疫苗保护机制",
    )

    assert result.analysis.answer == "这是根据本轮 PubMed 文献整理的科普回答。"
    assert [article.pmid for article in result.articles] == ["123"]
    assert client.responses.create.await_count == 2


@pytest.mark.asyncio
async def test_zero_result_retries_once_with_only_restrictive_syntax_removed() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _tool_response(
            "tool-response",
            name="pubmed_search",
            arguments={
                "query": '"HPV vaccine"[tiab] AND safety[tiab] NOT review[pt]',
                "max_results": 3,
            },
            call_id="empty-call",
        ),
        _final_response(),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    provider = FakePubMedProvider()
    recovered = PubMedArticle(pmid="456", title="Broadened search candidate")
    provider._search_articles = AsyncMock(side_effect=[[], [recovered]])

    result = await service.answer_with_pubmed_tools(
        ChatRequest(question="HPV 疫苗安全吗？"),
        RetrievalResult(chunks=[], context="", sources=[]),
        _assessment(),
        provider,
        rewritten_query="HPV 疫苗安全性",
    )

    assert provider._search_articles.await_args_list[0].args == (
        '"HPV vaccine"[tiab] AND safety[tiab] NOT review[pt]',
    )
    assert provider._search_articles.await_args_list[1].args == ("HPV vaccine AND safety",)
    assert [article.pmid for article in result.articles] == ["456"]
    output = json.loads(client.responses.create.await_args_list[1].kwargs["input"][0]["output"])
    assert output["search_trace"] == [
        {
            "attempt": "primary",
            "query": '"HPV vaccine"[tiab] AND safety[tiab] NOT review[pt]',
            "hit_count": 0,
            "provider": "fake",
        },
        {
            "attempt": "zero_result_fallback",
            "query": "HPV vaccine AND safety",
            "hit_count": 1,
            "provider": "fake",
        },
    ]


@pytest.mark.asyncio
async def test_zero_result_uses_model_supplied_broader_fallback_for_free_text_query() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _tool_response(
            "tool-response",
            name="pubmed_search",
            arguments={
                "query": "HPV vaccine safety effectiveness",
                "fallback_query": "HPV vaccine",
                "max_results": 2,
            },
            call_id="fallback-call",
        ),
        _final_response(),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    provider = FakePubMedProvider()
    provider._search_articles = AsyncMock(
        side_effect=[[], [PubMedArticle(pmid="789", title="Fallback candidate")]]
    )

    await service.answer_with_pubmed_tools(
        ChatRequest(question="HPV 疫苗安全性和有效性如何？"),
        RetrievalResult(chunks=[], context="", sources=[]),
        _assessment(),
        provider,
        rewritten_query="HPV 疫苗安全性和有效性",
    )

    assert [call.args[0] for call in provider._search_articles.await_args_list] == [
        "HPV vaccine safety effectiveness",
        "HPV vaccine",
    ]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            '"influenza vaccine"[Title/Abstract] AND effectiveness',
            "influenza vaccine AND effectiveness",
        ),
        ("influenza vaccine effectiveness", None),
        ("vaccine NOT review", "vaccine"),
    ],
)
def test_zero_result_broadening_never_invents_new_search_terms(
    query: str, expected: str | None
) -> None:
    assert _broaden_zero_result_query(query) == expected


@pytest.mark.asyncio
async def test_provider_outage_is_structured_for_model_and_final_answer_continues() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _tool_response(
            "tool-response",
            name="pubmed_search",
            arguments={"query": "HPV vaccine safety", "max_results": 3},
            call_id="outage-call",
        ),
        _final_response(),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    provider = FakePubMedProvider()
    provider._search_articles = AsyncMock(side_effect=PubMedUnavailableError)

    result = await service.answer_with_pubmed_tools(
        ChatRequest(question="最新 HPV 疫苗安全性研究"),
        RetrievalResult(chunks=[], context="", sources=[]),
        _assessment(),
        provider,
        rewritten_query="最新 HPV 疫苗安全性研究",
    )

    output = json.loads(client.responses.create.await_args_list[1].kwargs["input"][0]["output"])
    assert output == {"ok": False, "error": "PubMedUnavailableError"}
    assert result.articles == []
