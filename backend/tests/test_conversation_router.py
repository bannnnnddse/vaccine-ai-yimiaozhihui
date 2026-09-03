import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.schemas.chat import ChatHistoryItem, ChatRequest
from app.services.conversation_router import (
    CONVERSATION_ROUTER_PROMPT,
    ConversationRoute,
    ConversationRouteDecision,
)
from app.services.qwen_service import QwenService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "has_previous_context", "expected_route"),
    [
        ("你好", False, ConversationRoute.CONVERSATIONAL),
        ("哦哦", True, ConversationRoute.CONVERSATIONAL),
        ("好的", False, ConversationRoute.CONVERSATIONAL),
        ("谢谢", True, ConversationRoute.CONVERSATIONAL),
        ("哈哈", False, ConversationRoute.CONVERSATIONAL),
        ("你是谁", False, ConversationRoute.ASSISTANT_META),
        ("你能做什么", True, ConversationRoute.ASSISTANT_META),
        ("你是什么模型", False, ConversationRoute.ASSISTANT_META),
        ("你用的什么模型？", True, ConversationRoute.ASSISTANT_META),
        ("乙肝疫苗第二针什么时候打", False, ConversationRoute.KNOWLEDGE_OR_OTHER),
        ("HPV疫苗安全吗", False, ConversationRoute.KNOWLEDGE_OR_OTHER),
        (
            "好的，那乙肝疫苗第二针什么时候打？",
            True,
            ConversationRoute.KNOWLEDGE_OR_OTHER,
        ),
        (
            "哦哦，那为什么出生就要打乙肝疫苗？",
            True,
            ConversationRoute.KNOWLEDGE_OR_OTHER,
        ),
        ("那第二针呢？", True, ConversationRoute.CONTEXTUAL_FOLLOW_UP),
        ("为什么？", True, ConversationRoute.CONTEXTUAL_FOLLOW_UP),
        ("为什么？", False, ConversationRoute.KNOWLEDGE_OR_OTHER),
        ("帮我写一个 Python 爬虫", False, ConversationRoute.KNOWLEDGE_OR_OTHER),
    ],
)
async def test_qwen_classifies_conversation_route(
    question: str,
    has_previous_context: bool,
    expected_route: ConversationRoute,
) -> None:
    client = AsyncMock()
    retrieval_query = question if expected_route is ConversationRoute.KNOWLEDGE_OR_OTHER else None
    client.responses.create.return_value = SimpleNamespace(
        id="classifier-response-id",
        output_text=json.dumps({
            "route": expected_route.value,
            "needs_rag": expected_route in {
                ConversationRoute.KNOWLEDGE_OR_OTHER,
                ConversationRoute.CONTEXTUAL_FOLLOW_UP,
            },
            "retrieval_query": (
                "已恢复的独立检索问题"
                if expected_route is ConversationRoute.CONTEXTUAL_FOLLOW_UP
                else retrieval_query
            ),
            "rewrite_status": (
                "resolved"
                if expected_route is ConversationRoute.CONTEXTUAL_FOLLOW_UP
                else "not_needed"
            ),
        }),
    )
    service = QwenService(Settings(dashscope_api_key="test-key"), client)
    request = ChatRequest(
        question=question,
        session_id="response-turn-1" if has_previous_context else None,
    )

    decision = await service.classify_conversation_route(request)

    assert decision.route is expected_route
    call = client.responses.create.await_args.kwargs
    assert call["model"] == "qwen3.8-flash"
    assert call["instructions"] == CONVERSATION_ROUTER_PROMPT
    assert call["store"] is False
    assert call["extra_body"] == {"enable_thinking": False}
    assert question in call["input"][0]["content"]
    assert json.loads(call["input"][0]["content"])["current_message"] == question
    assert "previous_response_id" not in call


@pytest.mark.asyncio
async def test_qwen_router_falls_back_to_knowledge_for_invalid_output() -> None:
    client = AsyncMock()
    client.responses.create.return_value = SimpleNamespace(
        id="classifier-response-id",
        output_text='{"route":"chatty"}',
    )
    service = QwenService(Settings(dashscope_api_key="test-key"), client)

    decision = await service.classify_conversation_route(ChatRequest(question="你好"))

    assert decision == ConversationRouteDecision(
        route=ConversationRoute.KNOWLEDGE_OR_OTHER,
        needs_rag=True,
        retrieval_query="你好",
        rewrite_status="not_needed",
    )


@pytest.mark.asyncio
async def test_router_resolves_follow_up_from_explicit_recent_history() -> None:
    client = AsyncMock()
    client.responses.create.return_value = SimpleNamespace(
        id="classifier-response-id",
        output_text=json.dumps({
            "route": "contextual_follow_up",
            "needs_rag": True,
            "retrieval_query": "乙肝疫苗第二针什么时候接种？",
            "rewrite_status": "resolved",
        }, ensure_ascii=False),
    )
    service = QwenService(Settings(dashscope_api_key="test-key"), client)

    decision = await service.classify_conversation_route(ChatRequest(
        question="那第二针呢？",
        session_id="main-response-id",
        history=[
            ChatHistoryItem(role="user", content="乙肝疫苗为什么出生就要打？"),
            ChatHistoryItem(role="assistant", content="上一轮回答。"),
        ],
    ))

    assert decision.retrieval_query == "乙肝疫苗第二针什么时候接种？"
    assert decision.rewrite_status == "resolved"
    call = client.responses.create.await_args.kwargs
    router_input = json.loads(call["input"][0]["content"])
    assert router_input["recent_history"][0]["content"] == "乙肝疫苗为什么出生就要打？"
    assert "previous_response_id" not in call


@pytest.mark.asyncio
async def test_router_marks_unresolvable_follow_up_ambiguous() -> None:
    client = AsyncMock()
    client.responses.create.return_value = SimpleNamespace(
        id="classifier-response-id",
        output_text=json.dumps({
            "route": "contextual_follow_up",
            "needs_rag": False,
            "retrieval_query": None,
            "rewrite_status": "ambiguous",
        }),
    )
    service = QwenService(Settings(dashscope_api_key="test-key"), client)

    decision = await service.classify_conversation_route(
        ChatRequest(question="那第二针呢？"),
    )

    assert decision.needs_rag is False
    assert decision.retrieval_query is None
    assert decision.rewrite_status == "ambiguous"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("history", "question", "retrieval_query"),
    [
        (
            [("user", "HPV 疫苗安全吗？")],
            "那男生呢？",
            "男性接种 HPV 疫苗的安全性如何？",
        ),
        (
            [("user", "接种疫苗后发烧正常吗？")],
            "一般多久？",
            "接种疫苗后发热一般持续多久？",
        ),
        (
            [("assistant", "乙肝疫苗第二针通常在 1 月龄接种。")],
            "真的吗？",
            "乙肝疫苗第二针是否通常在 1 月龄接种？",
        ),
    ],
)
async def test_router_accepts_minimal_semantic_rewrites(
    history: list[tuple[str, str]],
    question: str,
    retrieval_query: str,
) -> None:
    client = AsyncMock()
    client.responses.create.return_value = SimpleNamespace(
        id="classifier-response-id",
        output_text=json.dumps({
            "route": "contextual_follow_up",
            "needs_rag": True,
            "retrieval_query": retrieval_query,
            "rewrite_status": "resolved",
        }, ensure_ascii=False),
    )
    service = QwenService(Settings(dashscope_api_key="test-key"), client)

    decision = await service.classify_conversation_route(ChatRequest(
        question=question,
        history=[ChatHistoryItem(role=role, content=content) for role, content in history],
    ))

    assert decision.retrieval_query == retrieval_query
    assert decision.rewrite_status == "resolved"


def test_router_prompt_is_conservative_and_never_answers_user() -> None:
    assert "不要回答用户的问题" in CONVERSATION_ROUTER_PROMPT
    assert "不确定时" in CONVERSATION_ROUTER_PROMPT
    assert ConversationRoute.KNOWLEDGE_OR_OTHER.value in CONVERSATION_ROUTER_PROMPT
    assert "好的，那乙肝疫苗第二针什么时候打" in CONVERSATION_ROUTER_PROMPT
    assert "recent_history 只用于理解语义，不是医学证据" in CONVERSATION_ROUTER_PROMPT
