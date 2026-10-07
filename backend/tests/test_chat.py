from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes.chat import (
    get_evidence_assessment_service,
    get_graph_service,
    get_knowledge_gap_service,
    get_pubmed_provider,
    get_qwen_service,
    get_rag_service,
)
from app.core.config import Settings
from app.graph.models import GraphRetrievalResult
from app.main import create_app
from app.pubmed.models import PubMedArticle
from app.rag.models import RagSource, RetrievedChunk
from app.rag.service import RetrievalResult
from app.rag.store import RagIndexNotReadyError
from app.schemas.chat import ChatResponse
from app.services.conversation_router import ConversationRoute, ConversationRouteDecision
from app.services.evidence_assessment import EvidenceAssessmentResult
from app.services.qwen_service import (
    PubMedAgentResult,
    PubMedEmptyEvidenceFinalizationError,
    QwenAuthenticationError,
    QwenContextExpiredError,
    QwenServiceError,
    QwenTimeoutError,
    VaccineQuestionAnalysis,
)


@pytest.fixture
def app():
    return create_app(
        Settings(
            _env_file=None,
            dashscope_api_key=None,
            pubmed_enabled=False,
        )
    )


def _stub_rag(app) -> Mock:
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    app.dependency_overrides[get_rag_service] = lambda: rag_service
    return rag_service


def _decision(
    route: ConversationRoute,
    *,
    retrieval_query: str | None = None,
    rewrite_status: str = "not_needed",
) -> ConversationRouteDecision:
    return ConversationRouteDecision(
        route=route,
        needs_rag=retrieval_query is not None,
        retrieval_query=retrieval_query,
        rewrite_status=rewrite_status,
    )


def test_chat_rejects_blank_question(app) -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "   ", "history": []})

    assert response.status_code == 422


def test_conversation_title_uses_shared_qwen_service(app) -> None:
    service = Mock()
    service.generate_conversation_title = AsyncMock(return_value="17岁男性九价HPV接种")
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/conversations/title",
            json={
                "messages": [
                    {"role": "user", "content": "我17岁男生，还能打九价HPV疫苗吗？"},
                    {"role": "assistant", "content": "请结合当地程序并咨询接种门诊。"},
                ]
            },
        )

    assert response.status_code == 200
    assert response.json() == {"title": "17岁男性九价HPV接种"}
    passed_messages = service.generate_conversation_title.await_args.args[0]
    assert [message.role for message in passed_messages] == ["user", "assistant"]


def test_conversation_title_failure_is_isolated_from_chat(app) -> None:
    service = Mock()
    service.generate_conversation_title = AsyncMock(side_effect=QwenServiceError)
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/conversations/title",
            json={
                "messages": [
                    {"role": "user", "content": "问题"},
                    {"role": "assistant", "content": "回答"},
                ]
            },
        )

    assert response.status_code == 502


def test_chat_rejects_question_longer_than_1000_characters(app) -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "疫" * 1001})

    assert response.status_code == 422


def test_chat_rejects_blank_session_id(app) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "疫苗有什么作用？", "session_id": "   "},
        )

    assert response.status_code == 422


def test_chat_rejects_session_id_longer_than_200_characters(app) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "疫苗有什么作用？", "session_id": "a" * 201},
        )

    assert response.status_code == 422


@pytest.mark.parametrize("session_id", ["", "   "])
def test_chat_response_rejects_blank_output_session_id(session_id: str) -> None:
    with pytest.raises(ValidationError):
        ChatResponse(
            answer="疫苗科普回答。",
            model="qwen3.8-flash",
            is_vaccine_related=True,
            session_id=session_id,
        )


def test_chat_source_normalizes_merged_document_pages() -> None:
    response = ChatResponse(
        answer="回答。",
        model="qwen3.8-flash",
        is_vaccine_related=True,
        session_id="response-turn",
        sources=[
            {
                "file_name": "接种规范.pdf",
                "page": 3,
                "pages": [7, 3, 7],
                "content": "第 3 页片段。\n\n第 7 页片段。",
            }
        ],
    )

    assert response.sources[0].pages == [3, 7]


def test_chat_without_api_key_returns_503(app) -> None:
    _stub_rag(app)
    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "疫苗有什么作用？"})

    assert response.status_code == 503
    assert len(response.headers["X-Trace-ID"]) == 32
    assert response.json() == {"detail": "AI 服务暂时不可用，请稍后重试。"}


def test_chat_returns_answer_from_qwen_service(app) -> None:
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="疫苗有什么作用？",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="这是经过模型生成的疫苗科普回答。",
        session_id="response-turn-2",
    )
    rag_service = _stub_rag(app)
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "question": " 疫苗有什么作用？ ",
                "history": [{"role": "user", "content": f"问题 {index}"} for index in range(12)],
            },
        )

    assert response.status_code == 200
    assert len(response.headers["X-Trace-ID"]) == 32
    assert response.headers["X-Trace-ID"].isalnum()
    assert response.json() == {
        "answer": "这是经过模型生成的疫苗科普回答。",
        "model": "qwen3.8-flash",
        "is_vaccine_related": True,
        "session_id": "response-turn-2",
        "sources": [],
    }
    service.analyze_question.assert_awaited_once()
    request = service.analyze_question.await_args.args[0]
    assert request.question == "疫苗有什么作用？"
    assert len(request.history) == 10
    rag_service.retrieve.assert_called_once()


def test_chat_stream_emits_real_stages_then_final_answer(app) -> None:
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="疫苗有什么作用？",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="这是流式接口返回的回答。",
        session_id="response-turn-stream",
    )
    rag_service = _stub_rag(app)
    rag_service.retrieve.return_value = RetrievalResult(
        chunks=[],
        context="",
        sources=[
            RagSource(
                file_name="疫苗规范.pdf",
                page=1,
                content="PDF 来源不应在流式结果中携带 null source_type。",
            )
        ],
    )
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post("/api/v1/chat/stream", json={"question": "疫苗有什么作用？"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: stage" in response.text
    assert "正在分析并改写科学问题" in response.text
    assert "正在检索本地文献库" in response.text
    assert "event: final" in response.text
    assert "这是流式接口返回的回答。" in response.text
    assert '"source_type": null' not in response.text


@pytest.mark.parametrize(
    ("question", "expected_route"),
    [
        ("哦哦", ConversationRoute.CONVERSATIONAL),
        ("你是什么模型", ConversationRoute.ASSISTANT_META),
    ],
)
def test_chat_bypasses_rag_for_non_knowledge_conversation(
    app,
    question: str,
    expected_route: ConversationRoute,
) -> None:
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(expected_route)
    service.respond_conversational.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=False,
        answer="自然简短回应。",
        session_id="response-turn-2",
    )
    rag_service = _stub_rag(app)
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": question, "session_id": "response-turn-1"},
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "自然简短回应。"
    assert response.json()["sources"] == []
    rag_service.retrieve.assert_not_called()
    service.classify_conversation_route.assert_awaited_once()
    service.analyze_question.assert_not_awaited()
    service.respond_conversational.assert_awaited_once()
    request, route = service.respond_conversational.await_args.args
    assert request.session_id == "response-turn-1"
    assert route is expected_route


def test_chat_keeps_knowledge_question_on_rag_path(app) -> None:
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="乙肝疫苗什么时候打",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="乙肝疫苗按免疫程序接种。",
        session_id="response-turn-2",
    )
    rag_service = _stub_rag(app)
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "乙肝疫苗什么时候打"},
        )

    assert response.status_code == 200
    rag_service.retrieve.assert_called_once_with("乙肝疫苗什么时候打")
    service.analyze_question.assert_awaited_once()
    service.respond_conversational.assert_not_awaited()
    analyzed_request = service.analyze_question.await_args.args[0]
    assert analyzed_request.question == "乙肝疫苗什么时候打"


def test_contextual_follow_up_sources_come_from_rewritten_current_turn_retrieval(app) -> None:
    retrieval = RetrievalResult(
        chunks=[],
        context='<knowledge source="1" file="程序.pdf" page="5">第二剂资料</knowledge>',
        sources=[RagSource(file_name="程序.pdf", page=5, content="第二剂资料")],
    )
    rag_service = _stub_rag(app)
    rag_service.retrieve.return_value = retrieval
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.CONTEXTUAL_FOLLOW_UP,
        retrieval_query="乙肝疫苗第二针什么时候接种？",
        rewrite_status="resolved",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="第二针回答。",
        session_id="response-turn-2",
    )
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "question": "那第二针呢？",
                "session_id": "response-turn-1",
                "history": [{"role": "user", "content": "乙肝疫苗为什么出生就要打？"}],
            },
        )

    assert response.status_code == 200
    rag_service.retrieve.assert_called_once_with("乙肝疫苗第二针什么时候接种？")
    request_used_by_main_llm, retrieval_used_by_main_llm = service.analyze_question.await_args.args
    assert request_used_by_main_llm.question == "那第二针呢？"
    assert retrieval_used_by_main_llm is retrieval
    assert service.analyze_question.await_args.kwargs == {
        "resolved_semantic_query": "乙肝疫苗第二针什么时候接种？"
    }
    assert response.json()["sources"] == [
        {"file_name": "程序.pdf", "page": 5, "content": "第二剂资料"},
    ]


@pytest.mark.parametrize(
    ("question", "session_id"),
    [
        ("好的，那乙肝疫苗第二针什么时候打？", None),
        ("那第二针呢？", "response-turn-1"),
    ],
)
def test_chat_keeps_compound_and_contextual_questions_on_rag_path(
    app,
    question: str,
    session_id: str | None,
) -> None:
    service = AsyncMock()
    service.classify_conversation_route.return_value = (
        _decision(
            ConversationRoute.CONTEXTUAL_FOLLOW_UP,
            retrieval_query="乙肝疫苗第二针什么时候接种？",
            rewrite_status="resolved",
        )
        if question == "那第二针呢？"
        else _decision(
            ConversationRoute.KNOWLEDGE_OR_OTHER,
            retrieval_query=question,
        )
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="保留原有知识问答路径。",
        session_id="response-turn-2",
    )
    rag_service = _stub_rag(app)
    app.dependency_overrides[get_qwen_service] = lambda: service
    payload = {"question": question}
    if session_id is not None:
        payload["session_id"] = session_id

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json=payload)

    assert response.status_code == 200
    rag_service.retrieve.assert_called_once_with(
        "乙肝疫苗第二针什么时候接种？" if question == "那第二针呢？" else question,
    )
    service.analyze_question.assert_awaited_once()
    service.respond_conversational.assert_not_awaited()
    analyzed_request = service.analyze_question.await_args.args[0]
    assert analyzed_request.question == question


def test_chat_returns_sources_from_retrieval(app) -> None:
    retrieval = RetrievalResult(
        chunks=[],
        context='<knowledge source="1" file="指南.pdf" page="12">片段</knowledge>',
        sources=[RagSource(file_name="指南.pdf", page=12, content="片段")],
    )
    rag_service = _stub_rag(app)
    rag_service.retrieve.return_value = retrieval
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="轻微感冒能接种吗？",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="回答。",
        session_id="response-turn-2",
    )
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "轻微感冒能接种吗？"})

    assert response.status_code == 200
    assert response.json()["sources"] == [{"file_name": "指南.pdf", "page": 12, "content": "片段"}]
    assert service.analyze_question.await_args.args[1] is retrieval


def test_chat_returns_empty_sources_for_non_vaccine_question(app) -> None:
    rag_service = _stub_rag(app)
    rag_service.retrieve.return_value = RetrievalResult(
        chunks=[],
        context='<knowledge source="1" file="指南.pdf" page="12">片段</knowledge>',
        sources=[RagSource(file_name="指南.pdf", page=12, content="片段")],
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="红烧肉怎么做？",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=False,
        answer="本助手只解答疫苗知识。",
        session_id="response-turn-2",
    )
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "红烧肉怎么做？"})

    assert response.status_code == 200
    assert response.json()["sources"] == []


def test_chat_returns_503_when_index_not_ready(app) -> None:
    rag_service = _stub_rag(app)
    rag_service.retrieve.side_effect = RagIndexNotReadyError()
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="疫苗有什么作用？",
    )
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "疫苗有什么作用？"})

    assert response.status_code == 503
    assert response.json() == {"detail": "本地知识库尚未建立，请先运行 RAG 建库命令。"}
    service.analyze_question.assert_not_awaited()


def test_chat_timeout_returns_504(app) -> None:
    _stub_rag(app)
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="接种后多久产生保护？",
    )
    service.analyze_question.side_effect = QwenTimeoutError
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "接种后多久产生保护？"})

    assert response.status_code == 504
    assert response.json() == {"detail": "网络超时，请稍后重试。"}


def test_chat_returns_409_when_context_has_expired(app) -> None:
    _stub_rag(app)
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.CONTEXTUAL_FOLLOW_UP,
        retrieval_query="乙肝疫苗第二针什么时候接种？",
        rewrite_status="resolved",
    )
    service.analyze_question.side_effect = QwenContextExpiredError
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "那第二针呢？", "session_id": "expired-response-id"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "本次会话已失效，请重新提问。"}


def test_chat_asks_for_clarification_without_rag_when_follow_up_is_ambiguous(app) -> None:
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.CONTEXTUAL_FOLLOW_UP,
        rewrite_status="ambiguous",
    )
    service.request_follow_up_clarification.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=False,
        answer="你指的是哪一种疫苗的第二针？",
        session_id="response-turn-1",
    )
    rag_service = _stub_rag(app)
    app.dependency_overrides[get_qwen_service] = lambda: service

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "那第二针呢？"})

    assert response.status_code == 200
    assert response.json()["answer"] == "你指的是哪一种疫苗的第二针？"
    assert response.json()["sources"] == []
    rag_service.retrieve.assert_not_called()
    service.request_follow_up_clarification.assert_awaited_once()
    service.analyze_question.assert_not_awaited()


def _partial_assessment() -> EvidenceAssessmentResult:
    return EvidenceAssessmentResult(
        status="partial",
        reason="缺少最新研究。",
        missing_aspects=["最新研究"],
        should_search_pubmed=True,
        trigger_reason="explicit_external_evidence_request",
        assessment_method="rule",
    )


def test_pubmed_enabled_partial_evidence_uses_agent_and_returns_compatible_sources() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    retrieval = RetrievalResult(
        chunks=[],
        context='<knowledge source="1" file="指南.pdf" page="12">本地片段</knowledge>',
        sources=[RagSource(file_name="指南.pdf", page=12, content="本地片段")],
    )
    rag_service = Mock()
    rag_service.retrieve.return_value = retrieval
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = _partial_assessment()
    provider = Mock()
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="最新 HPV 疫苗安全性研究",
    )
    service.answer_with_pubmed_tools.return_value = PubMedAgentResult(
        analysis=VaccineQuestionAnalysis(
            is_vaccine_related=True,
            answer="融合证据回答。",
            session_id="response-turn-2",
        ),
        articles=[
            PubMedArticle(
                pmid="12345678",
                title="HPV vaccine safety study",
                abstract="PubMed 摘要片段。",
                journal="Vaccine",
                publication_year=2025,
                doi="10.1/example",
            )
        ],
        tool_rounds=1,
    )
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: provider

    with TestClient(pubmed_app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "请给我最新 HPV 疫苗安全性研究"},
        )

    assert response.status_code == 200
    assert response.json()["sources"][0] == {
        "file_name": "指南.pdf",
        "page": 12,
        "content": "本地片段",
    }
    pubmed_source = response.json()["sources"][1]
    assert pubmed_source == {
        "file_name": "HPV vaccine safety study",
        "content": "PubMed 摘要片段。",
        "source_type": "pubmed",
        "source_title": "HPV vaccine safety study",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
        "title": "HPV vaccine safety study",
        "pmid": "12345678",
        "journal": "Vaccine",
        "year": 2025,
        "doi": "10.1/example",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
        "snippet": "PubMed 摘要片段。",
    }
    evidence_service.assess.assert_awaited_once_with(
        "最新 HPV 疫苗安全性研究",
        retrieval,
    )
    service.answer_with_pubmed_tools.assert_awaited_once()
    service.analyze_question.assert_not_awaited()


def test_pubmed_disabled_keeps_native_rag_without_assessment(app) -> None:
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="疫苗有什么作用？",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="本地回答。",
        session_id="response-turn-2",
    )
    rag_service = _stub_rag(app)
    evidence_service = AsyncMock()
    app.dependency_overrides[get_qwen_service] = lambda: service
    app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "疫苗有什么作用？"})

    assert response.status_code == 200
    evidence_service.assess.assert_not_awaited()
    service.analyze_question.assert_awaited_once()
    service.answer_with_pubmed_tools.assert_not_awaited()
    rag_service.retrieve.assert_called_once()


def test_graph_enabled_fuses_context_without_changing_chat_contract() -> None:
    graph_app = create_app(
        Settings(
            _env_file=None,
            dashscope_api_key=None,
            graph_rag_enabled=True,
            pubmed_enabled=False,
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="HPV疫苗为什么能降低宫颈癌风险？",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="融合图关系回答。",
        session_id="response-graph",
    )
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(
        chunks=[],
        context='<knowledge source="1" file="指南.pdf">向量证据</knowledge>',
        sources=[RagSource(file_name="指南.pdf", page=3, content="向量证据")],
    )
    graph_service = Mock()
    graph_service.retrieve.return_value = GraphRetrievalResult(
        paths=[object()],
        context=(
            '<graph_knowledge file="指南.pdf" chunk_id="chunk-1">'
            "HPV疫苗--预防-->HPV感染</graph_knowledge>"
        ),
        sources=[RagSource(file_name="指南.pdf", page=3, content="图关系证据")],
        trace={"status": "retrieved"},
    )
    graph_app.dependency_overrides[get_qwen_service] = lambda: service
    graph_app.dependency_overrides[get_rag_service] = lambda: rag_service
    graph_app.dependency_overrides[get_graph_service] = lambda: graph_service

    with TestClient(graph_app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "HPV疫苗为什么能降低宫颈癌风险？"},
        )

    assert response.status_code == 200
    assert set(response.json()) == {
        "answer",
        "model",
        "is_vaccine_related",
        "session_id",
        "sources",
    }
    fused = service.analyze_question.await_args.args[1]
    assert "<graph_knowledge" in fused.context
    assert response.json()["sources"] == [
        {
            "file_name": "指南.pdf",
            "page": 3,
            "content": "向量证据\n\n图关系证据",
        },
    ]


def test_graph_failure_falls_back_to_vector_retrieval() -> None:
    graph_app = create_app(
        Settings(
            _env_file=None,
            dashscope_api_key=None,
            graph_rag_enabled=True,
            pubmed_enabled=False,
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="疫苗保护机制是什么？",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="向量回答。",
        session_id="response-vector",
    )
    vector = RetrievalResult(chunks=[], context="vector-only", sources=[])
    rag_service = Mock()
    rag_service.retrieve.return_value = vector
    graph_service = Mock()
    graph_service.retrieve.side_effect = ValueError("corrupt graph")
    graph_app.dependency_overrides[get_qwen_service] = lambda: service
    graph_app.dependency_overrides[get_rag_service] = lambda: rag_service
    graph_app.dependency_overrides[get_graph_service] = lambda: graph_service

    with TestClient(graph_app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "疫苗保护机制是什么？"},
        )

    assert response.status_code == 200
    service.analyze_question.assert_awaited_once()
    assert service.analyze_question.await_args.args[1] is vector


def test_pubmed_agent_failure_does_not_fall_back_to_insufficient_local_rag() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="最新疫苗研究",
    )
    service.answer_with_pubmed_tools.side_effect = QwenServiceError
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = _partial_assessment()
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: Mock()

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": "最新疫苗研究"})

    assert response.status_code == 503
    assert "PubMed" in response.json()["detail"]
    service.analyze_question.assert_not_awaited()


def test_invalid_pubmed_final_with_no_evidence_uses_bounded_fallback() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="没有文献的疫苗问题",
    )
    service.answer_with_pubmed_tools.side_effect = PubMedEmptyEvidenceFinalizationError()
    service.respond_without_evidence.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="当前本地知识库和PubMed文献检索均没有相关研究或法规可以解答，我将用我自己的知识给您进行初步回答。\n\n这是受限的初步科普。",
        session_id="response-turn-fallback",
    )
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = _partial_assessment()
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: Mock()

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": "没有文献的疫苗问题"})

    assert response.status_code == 200
    assert response.json()["sources"] == []
    service.respond_without_evidence.assert_awaited_once()


def test_pubmed_agent_timeout_returns_network_timeout() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="最新疫苗研究",
    )
    service.answer_with_pubmed_tools.side_effect = QwenTimeoutError
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = _partial_assessment()
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: Mock()

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": "最新疫苗研究"})

    assert response.status_code == 504
    assert response.json() == {"detail": "网络超时，请稍后重试。"}
    service.respond_without_evidence.assert_not_awaited()


def test_pubmed_auth_failure_uses_bounded_fallback() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="最新疫苗研究",
    )
    service.answer_with_pubmed_tools.side_effect = QwenAuthenticationError
    service.respond_without_evidence.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="鉴权失败时先说明再用自身知识初步回答。",
        session_id="response-turn-auth-fallback",
    )
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = _partial_assessment()
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: Mock()

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": "最新疫苗研究"})

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert response.json()["session_id"] == "response-turn-auth-fallback"
    service.respond_without_evidence.assert_awaited_once()


def test_pubmed_empty_result_with_insufficient_local_evidence_uses_bounded_fallback() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="最新疫苗研究",
    )
    service.answer_with_pubmed_tools.return_value = PubMedAgentResult(
        analysis=VaccineQuestionAnalysis(
            is_vaccine_related=True,
            answer="没有文献时的工具回答。",
            session_id="response-turn-agent",
        ),
        articles=[],
        tool_rounds=1,
    )
    service.respond_without_evidence.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="本地证据不足且PubMed无结果时的受限初步回答。",
        session_id="response-turn-insufficient-fallback",
    )
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = _partial_assessment()
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(
        chunks=[
            RetrievedChunk(
                id="chunk-insufficient",
                file_name="指南.pdf",
                relative_path="指南.pdf",
                page=1,
                chunk_index=0,
                text="疫苗相关片段，但不足以支撑完整回答。",
                source_hash="hash-insufficient",
            )
        ],
        context="",
        sources=[],
    )
    provider = Mock()
    provider.max_results = 5
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: provider

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": "最新疫苗研究"})

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert response.json()["session_id"] == "response-turn-insufficient-fallback"
    service.respond_without_evidence.assert_awaited_once()


def test_pubmed_enabled_without_provider_rejects_insufficient_evidence() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="需要外部证据的问题",
    )
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = _partial_assessment()
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: None

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": "需要外部证据的问题"})

    assert response.status_code == 503
    assert "PubMed" in response.json()["detail"]
    evidence_service.assess.assert_awaited_once()
    service.analyze_question.assert_not_awaited()


def test_pubmed_identifier_fallback_returns_cited_articles_when_agent_returns_none() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    question = "Coxiella burnetii 暴露者接种 Q-VAX 前需要检查什么？"
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query=question,
    )
    service.answer_with_pubmed_tools.return_value = PubMedAgentResult(
        analysis=VaccineQuestionAnalysis(
            is_vaccine_related=True,
            answer="基于外部文献的回答。",
            session_id="response-turn-2",
        ),
        articles=[],
        tool_rounds=1,
    )
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = _partial_assessment()
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    provider = Mock()
    provider.max_results = 5
    provider.search_articles = AsyncMock(
        return_value=[PubMedArticle(pmid="40573946", title="Q-VAX evidence")]
    )
    provider.fetch_articles = AsyncMock(
        return_value=[
            PubMedArticle(
                pmid="40573946",
                title="Q-VAX evidence",
                abstract="Original PubMed abstract.",
            )
        ]
    )
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: provider

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": question})

    assert response.status_code == 200
    pubmed_source = response.json()["sources"][-1]
    assert pubmed_source["source_type"] == "pubmed"
    assert pubmed_source["pmid"] == "40573946"
    assert pubmed_source["content"] == "Original PubMed abstract."
    provider.search_articles.assert_awaited_once_with("Coxiella burnetii Q-VAX", max_results=5)
    provider.fetch_articles.assert_awaited_once_with(["40573946"])


def test_empty_local_and_pubmed_evidence_uses_bounded_fallback() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="罕见疫苗研究问题",
    )
    service.answer_with_pubmed_tools.return_value = PubMedAgentResult(
        analysis=VaccineQuestionAnalysis(
            is_vaccine_related=True,
            answer="没有文献时的工具回答。",
            session_id="response-turn-agent",
        ),
        articles=[],
        tool_rounds=1,
    )
    service.respond_without_evidence.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="当前本地知识库和PubMed文献检索均没有相关研究或法规可以解答，我将用我自己的知识给您进行初步回答。\n\n这是受限的初步科普。",
        session_id="response-turn-fallback",
    )
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = _partial_assessment()
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    provider = Mock()
    provider.max_results = 5
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: provider

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": "罕见疫苗研究问题"})

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert response.json()["session_id"] == "response-turn-fallback"
    service.respond_without_evidence.assert_awaited_once()


def test_conflicting_internal_evidence_triggers_pubmed_agent() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="本地指南与最新研究是否冲突",
    )
    service.answer_with_pubmed_tools.return_value = PubMedAgentResult(
        analysis=VaccineQuestionAnalysis(
            is_vaccine_related=True,
            answer="已区分本地指南与外部研究证据。",
            session_id="response-turn-2",
        ),
        articles=[PubMedArticle(pmid="12345678", title="PubMed evidence", abstract="Evidence")],
        tool_rounds=1,
    )
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = EvidenceAssessmentResult(
        status="conflict",
        reason="本地 Top-K 对核心结论存在冲突。",
        missing_aspects=["冲突结论的外部核验"],
        should_search_pubmed=True,
        trigger_reason="assessment_conflict",
        assessment_method="hybrid",
    )
    rag_service = Mock()
    retrieval = RetrievalResult(chunks=[], context="", sources=[])
    rag_service.retrieve.return_value = retrieval
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: Mock()

    with TestClient(pubmed_app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "本地指南与最新研究是否冲突"},
        )

    assert response.status_code == 200
    service.answer_with_pubmed_tools.assert_awaited_once()
    service.analyze_question.assert_not_awaited()


def test_sufficient_internal_evidence_keeps_local_answer_with_pubmed_enabled() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="疫苗如何产生免疫记忆",
    )
    service.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="本地证据足以回答。",
        session_id="response-turn-2",
    )
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = EvidenceAssessmentResult(
        status="sufficient",
        reason="Top-K 已覆盖核心问题。",
        missing_aspects=[],
        should_search_pubmed=False,
        trigger_reason=None,
        assessment_method="hybrid",
    )
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: Mock()

    with TestClient(pubmed_app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "疫苗如何产生免疫记忆"},
        )

    assert response.status_code == 200
    service.analyze_question.assert_awaited_once()
    service.answer_with_pubmed_tools.assert_not_awaited()


def test_conversational_boundary_skips_assessment_and_pubmed_when_enabled() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(ConversationRoute.CONVERSATIONAL)
    service.respond_conversational.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=False,
        answer="你好。",
        session_id="response-turn-1",
    )
    evidence_service = AsyncMock()
    rag_service = Mock()
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: Mock()

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": "你好"})

    assert response.status_code == 200
    rag_service.retrieve.assert_not_called()
    evidence_service.assess.assert_not_awaited()
    service.answer_with_pubmed_tools.assert_not_awaited()


def test_knowledge_gap_capture_is_optional_and_does_not_change_chat_response() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
            pubmed_create_knowledge_gap=True,
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="最新 HPV 疫苗研究",
    )
    article = PubMedArticle(pmid="12345678", title="HPV study", abstract="Evidence")
    service.answer_with_pubmed_tools.return_value = PubMedAgentResult(
        analysis=VaccineQuestionAnalysis(
            is_vaccine_related=True,
            answer="融合回答。",
            session_id="response-turn-2",
        ),
        articles=[article],
        tool_rounds=1,
    )
    evidence_service = AsyncMock()
    assessment = _partial_assessment()
    evidence_service.assess.return_value = assessment
    rag_service = Mock()
    retrieval = RetrievalResult(chunks=[], context="", sources=[])
    rag_service.retrieve.return_value = retrieval
    knowledge_gap_service = AsyncMock()
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: Mock()
    pubmed_app.dependency_overrides[get_knowledge_gap_service] = lambda: knowledge_gap_service

    with TestClient(pubmed_app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "最新 HPV 疫苗研究"},
        )

    assert response.status_code == 200
    knowledge_gap_service.capture_candidate.assert_awaited_once_with(
        original_query="最新 HPV 疫苗研究",
        rewritten_query="最新 HPV 疫苗研究",
        retrieval=retrieval,
        assessment=assessment,
        pubmed_articles=[article],
    )


def test_knowledge_gap_persistence_failure_does_not_fail_answer() -> None:
    pubmed_app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=True,
            pubmed_mcp_url="https://example.test/mcp",
            pubmed_create_knowledge_gap=True,
        )
    )
    service = AsyncMock()
    service.classify_conversation_route.return_value = _decision(
        ConversationRoute.KNOWLEDGE_OR_OTHER,
        retrieval_query="最新疫苗研究",
    )
    service.answer_with_pubmed_tools.return_value = PubMedAgentResult(
        analysis=VaccineQuestionAnalysis(
            is_vaccine_related=True,
            answer="回答仍然可用。",
            session_id="response-turn-2",
        ),
        articles=[PubMedArticle(pmid="12345678", title="PubMed evidence", abstract="Evidence")],
        tool_rounds=1,
    )
    evidence_service = AsyncMock()
    evidence_service.assess.return_value = EvidenceAssessmentResult(
        status="insufficient",
        reason="本地无证据。",
        missing_aspects=["外部核验"],
        should_search_pubmed=True,
        trigger_reason="no_internal_evidence",
        assessment_method="rule",
    )
    rag_service = Mock()
    rag_service.retrieve.return_value = RetrievalResult(chunks=[], context="", sources=[])
    knowledge_gap_service = AsyncMock()
    knowledge_gap_service.capture_candidate.side_effect = OSError("disk unavailable")
    pubmed_app.dependency_overrides[get_qwen_service] = lambda: service
    pubmed_app.dependency_overrides[get_rag_service] = lambda: rag_service
    pubmed_app.dependency_overrides[get_evidence_assessment_service] = lambda: evidence_service
    pubmed_app.dependency_overrides[get_pubmed_provider] = lambda: Mock()
    pubmed_app.dependency_overrides[get_knowledge_gap_service] = lambda: knowledge_gap_service

    with TestClient(pubmed_app) as client:
        response = client.post("/api/v1/chat", json={"question": "最新疫苗研究"})

    assert response.status_code == 200
    assert response.json()["answer"] == "回答仍然可用。"
