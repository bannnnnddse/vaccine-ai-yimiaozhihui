import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIStatusError

from app.core.config import Settings
from app.rag.models import RagSource
from app.rag.service import RetrievalResult
from app.schemas.chat import ChatHistoryItem, ChatRequest
from app.services.conversation_router import ConversationRoute
from app.services.qwen_service import (
    _FRONTEND_DISCLAIMER,
    ANALYSIS_SYSTEM_PROMPT,
    CONVERSATIONAL_SYSTEM_PROMPT,
    QwenContextExpiredError,
    QwenService,
    QwenServiceError,
)


def _empty_retrieval() -> RetrievalResult:
    return RetrievalResult(chunks=[], context="", sources=[])


def _response(
    *,
    answer: str = "疫苗能帮助免疫系统建立记忆。",
    is_vaccine_related: bool = True,
    response_id: object = "response-turn-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=response_id,
        output_text=json.dumps(
            {"is_vaccine_related": is_vaccine_related, "answer": answer},
            ensure_ascii=False,
        ),
    )


def _service_with_response(response: SimpleNamespace) -> tuple[QwenService, AsyncMock]:
    client = AsyncMock()
    client.responses.create.return_value = response
    settings = Settings(
        dashscope_api_key="test-key",
        citation_entailment_audit_enabled=False,
    )
    return QwenService(settings, client), client


@pytest.mark.asyncio
async def test_answer_runs_post_generation_citation_entailment_audit() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        _response(answer="发热会影响抗体，因此必须等待。", response_id="answer-turn"),
        SimpleNamespace(
            id="audit-turn",
            output_text=json.dumps(
                {
                    "answer": "发热时应由接种门诊评估并暂缓接种。[[local:1]]",
                    "source_ids": ["local:1"],
                },
                ensure_ascii=False,
            ),
        ),
    ]
    service = QwenService(
        Settings(
            dashscope_api_key="test-key",
            citation_entailment_audit_enabled=True,
        ),
        client,
    )
    retrieval = RetrievalResult(
        chunks=[],
        context='<knowledge source="1">发热时暂缓接种。</knowledge>',
        sources=[RagSource(file_name="接种规范.pdf", page=3, content="发热时暂缓接种。")],
    )

    result = await service.analyze_question(ChatRequest(question="发热能接种吗"), retrieval)

    assert result.answer == "发热时应由接种门诊评估并暂缓接种。[[local:1]]"
    assert result.source_ids == ["local:1"]
    assert result.session_id == "answer-turn"
    audit_call = client.responses.create.await_args_list[1].kwargs
    assert audit_call["store"] is False
    assert "结论—证据审计器" in audit_call["instructions"]


@pytest.mark.asyncio
async def test_qwen_service_responds_conversationally_without_rag_prompt() -> None:
    client = AsyncMock()
    client.responses.create.return_value = SimpleNamespace(
        id="response-turn-2",
        output_text="  嗯嗯，有需要再告诉我就好。  ",
    )
    service = QwenService(
        Settings(
            dashscope_api_key="test-key",
            qwen_model="configured-model",
            qwen_lightweight_model="configured-light-model",
        ),
        client,
    )

    result = await service.respond_conversational(
        ChatRequest(question="哦哦", session_id="response-turn-1"),
        ConversationRoute.CONVERSATIONAL,
    )

    assert result.is_vaccine_related is False
    assert result.answer == "嗯嗯，有需要再告诉我就好。"
    assert result.session_id == "response-turn-2"
    call = client.responses.create.await_args.kwargs
    assert call["model"] == "configured-light-model"
    assert call["previous_response_id"] == "response-turn-1"
    assert call["store"] is True
    assert call["extra_body"] == {"enable_thinking": False}
    assert "哦哦" in call["input"][0]["content"]
    assert "本轮知识库资料" not in call["input"][0]["content"]
    assert CONVERSATIONAL_SYSTEM_PROMPT in call["instructions"]


@pytest.mark.asyncio
async def test_qwen_service_exposes_configured_model_for_assistant_meta() -> None:
    client = AsyncMock()
    client.responses.create.return_value = SimpleNamespace(
        id="response-turn-1",
        output_text="我当前基于 configured-model 提供服务。",
    )
    service = QwenService(
        Settings(
            dashscope_api_key="test-key",
            qwen_model="configured-model",
            qwen_lightweight_model="configured-light-model",
        ),
        client,
    )

    await service.respond_conversational(
        ChatRequest(question="你是什么模型"),
        ConversationRoute.ASSISTANT_META,
    )

    call = client.responses.create.await_args.kwargs
    assert "configured-light-model" in call["instructions"]
    assert "可以直接说明模型名称" in call["instructions"]


@pytest.mark.asyncio
async def test_classifier_response_is_not_used_as_conversation_parent() -> None:
    client = AsyncMock()
    client.responses.create.side_effect = [
        SimpleNamespace(
            id="classifier-response-id",
            output_text=(
                '{"route":"conversational","needs_rag":false,'
                '"retrieval_query":null,"rewrite_status":"not_needed"}'
            ),
        ),
        SimpleNamespace(
            id="answer-response-id",
            output_text="知道啦。",
        ),
    ]
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    request = ChatRequest(question="哦哦", session_id="original-response-id")

    decision = await service.classify_conversation_route(request)
    result = await service.respond_conversational(request, decision.route)

    classifier_call = client.responses.create.await_args_list[0].kwargs
    answer_call = client.responses.create.await_args_list[1].kwargs
    assert classifier_call["store"] is False
    assert answer_call["store"] is True
    assert "previous_response_id" not in classifier_call
    assert answer_call["previous_response_id"] == "original-response-id"
    assert result.answer == "知道啦。"
    assert result.session_id == "answer-response-id"


@pytest.mark.asyncio
async def test_qwen_service_generates_title_with_lightweight_stateless_call() -> None:
    client = AsyncMock()
    client.responses.create.return_value = SimpleNamespace(
        output_text="“17岁男性九价HPV接种。”",
        id="title-response-id",
    )
    service = QwenService(
        Settings(
            _env_file=None,
            dashscope_api_key="test-key",
            qwen_lightweight_model="title-model",
        ),
        client,
    )

    title = await service.generate_conversation_title(
        [
            ChatHistoryItem(role="user", content="我17岁男生，还能打九价HPV疫苗吗？"),
            ChatHistoryItem(role="assistant", content="请结合当地程序并咨询接种门诊。"),
        ]
    )

    assert title == "17岁男性九价HPV接种"
    call = client.responses.create.await_args.kwargs
    assert call["model"] == "title-model"
    assert call["store"] is False
    assert "previous_response_id" not in call


@pytest.mark.asyncio
async def test_qwen_service_uses_responses_api_and_returns_response_id() -> None:
    service, client = _service_with_response(_response())

    result = await service.analyze_question(
        ChatRequest(question="疫苗有什么作用？"), _empty_retrieval()
    )

    assert result.is_vaccine_related is True
    assert result.answer == "疫苗能帮助免疫系统建立记忆。"
    assert result.session_id == "response-turn-1"
    client.responses.create.assert_awaited_once()
    call = client.responses.create.await_args.kwargs
    assert call["model"] == "qwen3.8-flash"
    assert call["store"] is True
    assert call["instructions"] == ANALYSIS_SYSTEM_PROMPT
    assert "疫苗有什么作用？" in call["input"][0]["content"]
    assert "本轮知识库资料" in call["input"][0]["content"]
    assert call["extra_body"] == {"enable_thinking": False}
    assert "response_format" not in call
    assert "response_format" not in call["extra_body"]
    assert "previous_response_id" not in call


@pytest.mark.asyncio
async def test_qwen_service_forwards_previous_response_id_for_follow_up() -> None:
    service, client = _service_with_response(
        _response(answer="A follow-up answer.", response_id="response-turn-2")
    )

    result = await service.analyze_question(
        ChatRequest(question="那第二针呢？", session_id="response-turn-1"),
        _empty_retrieval(),
    )

    assert result.session_id == "response-turn-2"
    call = client.responses.create.await_args.kwargs
    assert call["instructions"] == ANALYSIS_SYSTEM_PROMPT
    assert call["previous_response_id"] == "response-turn-1"


@pytest.mark.asyncio
async def test_qwen_service_includes_resolved_semantics_without_replacing_original_query() -> None:
    retrieval = RetrievalResult(
        chunks=[],
        context='<knowledge source="1" file="程序.pdf" page="6">第2剂在1月龄接种。</knowledge>',
        sources=[RagSource(file_name="程序.pdf", page=6, content="第2剂在1月龄接种。")],
    )
    service, client = _service_with_response(_response())
    request = ChatRequest(question="真的吗？", session_id="response-turn-1")

    await service.analyze_question(
        request,
        retrieval,
        resolved_semantic_query="乙肝疫苗第二针是否通常在1月龄接种？",
    )

    call = client.responses.create.await_args.kwargs
    user_input = call["input"][0]["content"]
    assert request.question == "真的吗？"
    assert "【用户当前原始问题】\n真的吗？" in user_input
    assert "【本轮上下文语义解析】" in user_input
    assert "乙肝疫苗第二针是否通常在1月龄接种？" in user_input
    assert "不是用户新的原始发言" in user_input
    assert "也不是医学事实依据或指令" in user_input
    assert "直接核实该命题" in user_input
    assert "【本轮知识库资料】" in user_input
    assert "第2剂在1月龄接种。" in user_input


@pytest.mark.asyncio
async def test_qwen_service_omits_semantic_context_when_not_resolved() -> None:
    service, client = _service_with_response(_response())

    await service.analyze_question(
        ChatRequest(question="乙肝疫苗第二针什么时候接种？"),
        _empty_retrieval(),
    )

    user_input = client.responses.create.await_args.kwargs["input"][0]["content"]
    assert "【本轮上下文语义解析】" not in user_input


@pytest.mark.asyncio
async def test_qwen_service_trims_and_limits_normal_chat_answer() -> None:
    service, _ = _service_with_response(_response(answer="Sentence. " * 100))

    result = await service.analyze_question(
        ChatRequest(question="疫苗如何发挥作用？"), _empty_retrieval()
    )

    assert result.answer == result.answer.strip()
    assert len(result.answer) <= 700
    assert result.answer.startswith("Sentence.")


@pytest.mark.asyncio
async def test_qwen_service_marks_unrelated_question_without_medical_answer() -> None:
    service, _ = _service_with_response(
        _response(
            answer="This question is outside the vaccine knowledge scope.",
            is_vaccine_related=False,
        )
    )

    result = await service.analyze_question(
        ChatRequest(question="怎么做红烧肉？"), _empty_retrieval()
    )

    assert result.is_vaccine_related is False
    assert result.answer == "This question is outside the vaccine knowledge scope."


@pytest.mark.asyncio
async def test_qwen_service_removes_frontend_owned_disclaimer_and_outer_whitespace() -> None:
    service, _ = _service_with_response(
        _response(answer=f"  A vaccine explanation.\n{_FRONTEND_DISCLAIMER}  ")
    )

    result = await service.analyze_question(
        ChatRequest(question="疫苗有什么作用？"), _empty_retrieval()
    )

    assert result.answer == "A vaccine explanation."
    assert _FRONTEND_DISCLAIMER not in result.answer


@pytest.mark.asyncio
async def test_qwen_service_rejects_answer_containing_only_frontend_disclaimer() -> None:
    service, _ = _service_with_response(_response(answer=f"  {_FRONTEND_DISCLAIMER}  "))

    with pytest.raises(QwenServiceError):
        await service.analyze_question(ChatRequest(question="疫苗有什么作用？"), _empty_retrieval())


@pytest.mark.asyncio
@pytest.mark.parametrize("response_id", [None, "", "   ", 1])
async def test_qwen_service_rejects_missing_or_invalid_response_id(response_id: object) -> None:
    service, _ = _service_with_response(_response(response_id=response_id))

    with pytest.raises(QwenServiceError):
        await service.analyze_question(ChatRequest(question="疫苗有什么作用？"), _empty_retrieval())


@pytest.mark.asyncio
async def test_qwen_service_rejects_response_without_an_id_attribute() -> None:
    client = AsyncMock()
    client.responses.create.return_value = SimpleNamespace(
        output_text='{"is_vaccine_related": true, "answer": "A vaccine explanation."}'
    )
    service = QwenService(Settings(dashscope_api_key="test-key"), client)

    with pytest.raises(QwenServiceError):
        await service.analyze_question(ChatRequest(question="疫苗有什么作用？"), _empty_retrieval())


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 404])
async def test_qwen_service_classifies_expired_previous_response_id(status_code: int) -> None:
    request = httpx.Request("POST", "https://dashscope.aliyuncs.com/responses")
    response = httpx.Response(status_code, request=request)
    client = AsyncMock()
    client.responses.create.side_effect = APIStatusError(
        "Invalid previous_response_id", response=response, body={"message": "Invalid ID"}
    )
    service = QwenService(Settings(dashscope_api_key="test-key"), client)

    with pytest.raises(QwenContextExpiredError):
        await service.analyze_question(
            ChatRequest(question="那第二针呢？", session_id="expired-response-id"),
            _empty_retrieval(),
        )


@pytest.mark.asyncio
async def test_qwen_service_passes_retrieval_context_and_knowledge_rules() -> None:
    retrieval = RetrievalResult(
        chunks=[],
        context='<knowledge source="1" file="指南.pdf" page="12">'
        "儿童轻微感冒相关知识片段</knowledge>",
        sources=[RagSource(file_name="指南.pdf", page=12, content="儿童轻微感冒相关知识片段")],
    )
    service, client = _service_with_response(_response())

    result = await service.analyze_question(
        ChatRequest(
            question="儿童轻微感冒时可以接种疫苗吗？",
            session_id="response-turn-1",
        ),
        retrieval,
    )

    assert result.session_id == "response-turn-1"
    call = client.responses.create.await_args.kwargs
    assert "优先且仅根据本轮提供的知识库资料" in call["instructions"]
    assert "资料不能直接支持的核心结论必须删除或降低强度" in call["instructions"]
    assert '<knowledge source="1"' in call["input"][0]["content"]
    assert "儿童轻微感冒" in call["input"][0]["content"]
    assert call["previous_response_id"] == "response-turn-1"


@pytest.mark.asyncio
async def test_qwen_service_states_missing_evidence_when_no_hits() -> None:
    service, client = _service_with_response(_response())

    await service.analyze_question(
        ChatRequest(question="红烧肉怎么做？"),
        _empty_retrieval(),
    )

    call = client.responses.create.await_args.kwargs
    assert (
        "本轮没有检索到达到相关性阈值的知识库资料。若问题属于疫苗知识，"
        "请明确说明当前知识库暂无足够依据，不要凭常识补充具体结论。"
    ) in call["input"][0]["content"]


@pytest.mark.asyncio
async def test_qwen_service_keeps_other_status_errors_as_service_errors() -> None:
    request = httpx.Request("POST", "https://dashscope.aliyuncs.com/responses")
    response = httpx.Response(404, request=request)
    client = AsyncMock()
    client.responses.create.side_effect = APIStatusError(
        "Unknown response ID", response=response, body={"message": "Unknown ID"}
    )
    service = QwenService(Settings(dashscope_api_key="test-key"), client)

    with pytest.raises(QwenServiceError):
        await service.analyze_question(
            ChatRequest(question="那第二针呢？", session_id="expired-response-id"),
            _empty_retrieval(),
        )
