import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.observability import current_trace_id, timed_stage
from app.graph.fusion import fuse_retrieval_context
from app.graph.service import GraphService
from app.graph.storage import GraphStoreError
from app.pubmed.models import PubMedArticle
from app.pubmed.provider import PubMedProvider, PubMedProviderError
from app.pubmed.query import build_identifier_query
from app.rag.service import RagService
from app.rag.store import RagIndexNotReadyError, RagStoreError
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSource,
    ConversationTitleRequest,
    ConversationTitleResponse,
)
from app.services.conversation_router import ConversationRoute
from app.services.evidence_assessment import EvidenceAssessmentService
from app.services.knowledge_gap_service import KnowledgeGapService
from app.services.qwen_service import (
    PubMedFinalizationError,
    QwenAuthenticationError,
    QwenContextExpiredError,
    QwenNotConfiguredError,
    QwenService,
    QwenServiceError,
    QwenTimeoutError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI 问答"])
UNAVAILABLE_DETAIL = "AI 服务暂时不可用，请稍后重试。"
TIMEOUT_DETAIL = "网络超时，请稍后重试。"
CONTEXT_EXPIRED_DETAIL = "本次会话已失效，请重新提问。"
RAG_NOT_READY_DETAIL = "本地知识库尚未建立，请先运行 RAG 建库命令。"
PUBMED_EVIDENCE_UNAVAILABLE_DETAIL = (
    "当前问题需要 PubMed 外部文献核验，但文献检索暂不可用，请稍后重试。"
)
ChatProgressCallback = Callable[[str], Awaitable[None]]


async def _emit_progress(callback: ChatProgressCallback | None, message: str) -> None:
    if callback is not None:
        await callback(message)


def get_qwen_service(request: Request) -> QwenService:
    return request.app.state.qwen_service


def get_rag_service(request: Request) -> RagService:
    return request.app.state.rag_service


def get_graph_service(request: Request) -> GraphService:
    return request.app.state.graph_service


def get_evidence_assessment_service(request: Request) -> EvidenceAssessmentService:
    return request.app.state.evidence_assessment_service


def get_pubmed_provider(request: Request) -> PubMedProvider | None:
    return request.app.state.pubmed_provider


def get_knowledge_gap_service(request: Request) -> KnowledgeGapService | None:
    return request.app.state.knowledge_gap_service


@router.post(
    "/conversations/title",
    response_model=ConversationTitleResponse,
)
async def conversation_title(
    payload: ConversationTitleRequest,
    service: Annotated[QwenService, Depends(get_qwen_service)],
) -> ConversationTitleResponse:
    try:
        title = await service.generate_conversation_title(payload.messages)
    except QwenNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UNAVAILABLE_DETAIL,
        ) from exc
    except QwenTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=TIMEOUT_DETAIL,
        ) from exc
    except (QwenAuthenticationError, QwenServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=UNAVAILABLE_DETAIL,
        ) from exc
    return ConversationTitleResponse(title=title)


async def _execute_chat(
    payload: ChatRequest,
    service: Annotated[QwenService, Depends(get_qwen_service)],
    rag_service: Annotated[RagService, Depends(get_rag_service)],
    graph_service: Annotated[GraphService, Depends(get_graph_service)],
    evidence_service: Annotated[
        EvidenceAssessmentService,
        Depends(get_evidence_assessment_service),
    ],
    pubmed_provider: Annotated[PubMedProvider | None, Depends(get_pubmed_provider)],
    knowledge_gap_service: Annotated[
        KnowledgeGapService | None,
        Depends(get_knowledge_gap_service),
    ],
    request: Request,
    progress_callback: ChatProgressCallback | None = None,
) -> ChatResponse:
    pubmed_articles: list[PubMedArticle] = []
    assessment = None
    pubmed_attempted = False
    pubmed_agent_fallback = False
    no_evidence_fallback = False
    graph_status = "disabled"
    try:
        await _emit_progress(progress_callback, "正在分析并改写科学问题…")
        with timed_stage(logger, "router"):
            route_decision = await service.classify_conversation_route(payload)
    except QwenNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UNAVAILABLE_DETAIL,
        ) from exc
    except QwenTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=TIMEOUT_DETAIL,
        ) from exc
    except QwenContextExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CONTEXT_EXPIRED_DETAIL,
        ) from exc
    except (QwenAuthenticationError, QwenServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=UNAVAILABLE_DETAIL,
        ) from exc
    conversation_route = route_decision.route
    bypasses_rag = conversation_route in {
        ConversationRoute.CONVERSATIONAL,
        ConversationRoute.ASSISTANT_META,
    }
    retrieval = None
    vector_retrieval = None
    if route_decision.needs_rag:
        try:
            await _emit_progress(progress_callback, "正在检索本地文献库…")
            loop = asyncio.get_running_loop()

            def report_rag_progress(stage: str) -> None:
                labels = {
                    "dense": "正在检索语义证据…",
                    "bm25": "正在检索关键词证据…",
                    "reranker": "正在重排证据…",
                }
                message = labels.get(stage)
                if message and progress_callback is not None:
                    loop.call_soon_threadsafe(
                        asyncio.create_task,
                        _emit_progress(progress_callback, message),
                    )

            with timed_stage(logger, "rag_total"):
                async with request.app.state.rag_semaphore:
                    if progress_callback is None:
                        retrieval = await run_in_threadpool(
                            rag_service.retrieve,
                            route_decision.retrieval_query,
                        )
                    else:
                        retrieval = await run_in_threadpool(
                            rag_service.retrieve,
                            route_decision.retrieval_query,
                            progress_callback=report_rag_progress,
                        )
            vector_retrieval = retrieval
        except RagIndexNotReadyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=RAG_NOT_READY_DETAIL,
            ) from exc
        except RagStoreError as exc:
            logger.warning("本地 RAG 检索失败: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=UNAVAILABLE_DETAIL,
            ) from exc

        if request.app.state.settings.graph_rag_enabled:
            try:
                graph_retrieval = await run_in_threadpool(
                    graph_service.retrieve,
                    route_decision.retrieval_query,
                )
                graph_status = str(graph_retrieval.trace.get("status", "unknown"))
                retrieval = fuse_retrieval_context(
                    retrieval,
                    graph_retrieval,
                    max_context_chars=request.app.state.settings.rag_max_context_chars,
                )
            except (GraphStoreError, FileNotFoundError, ValueError, OSError) as exc:
                graph_status = "fallback"
                logger.warning(
                    "GraphRAG unavailable; using vector retrieval: %s",
                    type(exc).__name__,
                )

    try:
        if route_decision.rewrite_status == "ambiguous":
            await _emit_progress(progress_callback, "正在生成澄清问题…")
            with timed_stage(logger, "final_answer", mode="clarification"):
                analysis = await service.request_follow_up_clarification(payload)
        elif bypasses_rag:
            await _emit_progress(progress_callback, "正在生成回答…")
            with timed_stage(logger, "final_answer", mode=conversation_route.value):
                analysis = await service.respond_conversational(payload, conversation_route)
        else:
            if retrieval is None:
                raise QwenServiceError
            if pubmed_provider is not None or request.app.state.settings.pubmed_enabled:
                await _emit_progress(progress_callback, "正在评估本地证据充分性…")
                with timed_stage(logger, "evidence_assessment"):
                    assessment = await evidence_service.assess(
                        route_decision.retrieval_query,
                        vector_retrieval,
                    )
            if assessment is not None and assessment.should_search_pubmed:
                if pubmed_provider is None:
                    logger.error(
                        "PubMed evidence required but provider is unavailable "
                        "trace_id=%s trigger=%s error_type=PubMedUnavailableError",
                        current_trace_id(),
                        assessment.trigger_reason,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=PUBMED_EVIDENCE_UNAVAILABLE_DETAIL,
                    )
                try:
                    pubmed_attempted = True
                    await _emit_progress(progress_callback, "正在调用 PubMed 检索工具…")
                    with timed_stage(logger, "pubmed_orchestration"):
                        agent_result = await service.answer_with_pubmed_tools(
                            payload,
                            retrieval,
                            assessment,
                            pubmed_provider,
                            rewritten_query=route_decision.retrieval_query,
                            max_tool_rounds=request.app.state.settings.pubmed_max_tool_rounds,
                        )
                    analysis = agent_result.analysis
                    pubmed_articles = agent_result.articles
                except PubMedFinalizationError as exc:
                    pubmed_agent_fallback = True
                    no_evidence_fallback = True
                    pubmed_articles = exc.articles
                    logger.warning(
                        "PubMed final JSON was invalid; retaining fetched articles and using "
                        "bounded fallback trace_id=%s error_type=final_json_invalid "
                        "articles=%d cause=%s",
                        current_trace_id(),
                        len(pubmed_articles),
                        type(exc.__cause__).__name__ if exc.__cause__ is not None else "none",
                    )
                    await _emit_progress(progress_callback, "正在生成受限的初步回答…")
                    with timed_stage(logger, "final_answer", mode="no_evidence_fallback"):
                        analysis = await service.respond_without_evidence(payload)
                except QwenAuthenticationError:
                    pubmed_agent_fallback = True
                    no_evidence_fallback = True
                    logger.warning(
                        "PubMed Agent 鉴权失败，改用受限初步回答 "
                        "trace_id=%s error_type=PubMedAgentAuthFailure",
                        current_trace_id(),
                    )
                    await _emit_progress(progress_callback, "正在生成受限的初步回答…")
                    with timed_stage(logger, "final_answer", mode="no_evidence_fallback"):
                        analysis = await service.respond_without_evidence(payload)
                except QwenTimeoutError as exc:
                    pubmed_agent_fallback = True
                    raise HTTPException(
                        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                        detail=TIMEOUT_DETAIL,
                    ) from exc
                except QwenServiceError as exc:
                    pubmed_agent_fallback = True
                    logger.warning("PubMed Agent 失败，拒绝使用不充分的本地证据回答")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=PUBMED_EVIDENCE_UNAVAILABLE_DETAIL,
                    ) from exc
                if not pubmed_articles and not no_evidence_fallback:
                    pubmed_articles = await _search_pubmed_by_identifiers(
                        pubmed_provider,
                        route_decision.retrieval_query,
                    )
                if not pubmed_articles and not no_evidence_fallback:
                    no_evidence_fallback = True
                    logger.warning(
                        "PubMed evidence required but no articles were returned; "
                        "using bounded fallback trace_id=%s trigger=%s "
                        "error_type=PubMedEmptyResultError",
                        current_trace_id(),
                        assessment.trigger_reason,
                    )
                    await _emit_progress(progress_callback, "正在生成受限的初步回答…")
                    with timed_stage(logger, "final_answer", mode="no_evidence_fallback"):
                        analysis = await service.respond_without_evidence(payload)
                    logger.info(
                        "Using bounded no-evidence fallback trace_id=%s",
                        current_trace_id(),
                    )
            else:
                await _emit_progress(progress_callback, "正在整理最终回答…")
                with timed_stage(logger, "final_answer", mode="knowledge"):
                    analysis = await service.analyze_question(
                        payload,
                        retrieval,
                        resolved_semantic_query=(
                            route_decision.retrieval_query
                            if route_decision.rewrite_status == "resolved"
                            else None
                        ),
                    )
    except QwenNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UNAVAILABLE_DETAIL,
        ) from exc
    except QwenTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=TIMEOUT_DETAIL,
        ) from exc
    except QwenContextExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CONTEXT_EXPIRED_DETAIL,
        ) from exc
    except (QwenAuthenticationError, QwenServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=UNAVAILABLE_DETAIL,
        ) from exc

    logger.info(
        "chat orchestration trace_id=%s route=%s rewrite_status=%s rag_used=%s rag_hits=%d "
        "evidence_status=%s pubmed_trigger=%s pubmed_attempted=%s "
        "pubmed_articles=%d pubmed_agent_fallback=%s graph_status=%s",
        current_trace_id(),
        conversation_route.value,
        route_decision.rewrite_status,
        retrieval is not None,
        len(retrieval.chunks) if retrieval is not None else 0,
        assessment.status if assessment is not None else None,
        assessment.trigger_reason if assessment is not None else None,
        pubmed_attempted,
        len(pubmed_articles),
        pubmed_agent_fallback,
        graph_status,
    )
    if (
        knowledge_gap_service is not None
        and assessment is not None
        and retrieval is not None
        and analysis.is_vaccine_related
        and not no_evidence_fallback
    ):
        try:
            await knowledge_gap_service.capture_candidate(
                original_query=payload.question,
                rewritten_query=route_decision.retrieval_query,
                retrieval=vector_retrieval,
                assessment=assessment,
                pubmed_articles=pubmed_articles,
            )
        except Exception as exc:  # candidate capture must never fail the user answer
            logger.warning("KnowledgeGap 候选记录失败: %s", type(exc).__name__)
    internal_sources = [
        ChatSource(
            file_name=item.file_name,
            page=item.page,
            content=item.content,
            source_type=item.source_type if item.source_type != "pdf" else None,
            source_title=item.source_title,
            source_url=item.source_url,
            section=item.section,
        )
        for item in retrieval.sources
    ] if retrieval is not None and analysis.is_vaccine_related else []
    external_sources = [
        ChatSource(
            file_name=article.title,
            page=None,
            content=(article.abstract[:1200] or article.title),
            source_type="pubmed",
            source_title=article.title,
            source_url=article.url,
            title=article.title,
            pmid=article.pmid,
            journal=article.journal or None,
            year=article.publication_year,
            doi=article.doi,
            url=article.url,
            snippet=(article.abstract[:1200] or article.title),
        )
        for article in pubmed_articles
    ] if analysis.is_vaccine_related else []
    return ChatResponse(
        answer=analysis.answer,
        model=request.app.state.settings.qwen_model,
        is_vaccine_related=analysis.is_vaccine_related,
        session_id=analysis.session_id,
        sources=[*internal_sources, *external_sources],
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    response_model_exclude_none=True,
)
async def chat(
    payload: ChatRequest,
    service: Annotated[QwenService, Depends(get_qwen_service)],
    rag_service: Annotated[RagService, Depends(get_rag_service)],
    graph_service: Annotated[GraphService, Depends(get_graph_service)],
    evidence_service: Annotated[
        EvidenceAssessmentService,
        Depends(get_evidence_assessment_service),
    ],
    pubmed_provider: Annotated[PubMedProvider | None, Depends(get_pubmed_provider)],
    knowledge_gap_service: Annotated[
        KnowledgeGapService | None,
        Depends(get_knowledge_gap_service),
    ],
    request: Request,
) -> ChatResponse:
    return await _execute_chat(
        payload,
        service,
        rag_service,
        graph_service,
        evidence_service,
        pubmed_provider,
        knowledge_gap_service,
        request,
    )


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    service: Annotated[QwenService, Depends(get_qwen_service)],
    rag_service: Annotated[RagService, Depends(get_rag_service)],
    graph_service: Annotated[GraphService, Depends(get_graph_service)],
    evidence_service: Annotated[
        EvidenceAssessmentService,
        Depends(get_evidence_assessment_service),
    ],
    pubmed_provider: Annotated[PubMedProvider | None, Depends(get_pubmed_provider)],
    knowledge_gap_service: Annotated[
        KnowledgeGapService | None,
        Depends(get_knowledge_gap_service),
    ],
    request: Request,
) -> StreamingResponse:
    trace_id = current_trace_id()
    events: asyncio.Queue[tuple[str, dict[str, object]]] = asyncio.Queue()

    async def emit(message: str) -> None:
        await events.put(("stage", {"message": message}))

    async def run_chat() -> None:
        from app.core.observability import reset_trace_id, set_trace_id

        token = set_trace_id(trace_id)
        try:
            result = await _execute_chat(
                payload,
                service,
                rag_service,
                graph_service,
                evidence_service,
                pubmed_provider,
                knowledge_gap_service,
                request,
                progress_callback=emit,
            )
            # Keep the stream payload byte-for-byte compatible with the normal
            # response model. In particular, PDF sources omit source_type;
            # emitting it as null makes the frontend reject an otherwise valid
            # source as an unknown type.
            await events.put(("final", result.model_dump(mode="json", exclude_none=True)))
        except HTTPException as exc:
            await events.put(("error", {"status": exc.status_code, "detail": str(exc.detail)}))
        except Exception:
            logger.exception("chat stream failed trace_id=%s", trace_id)
            await events.put(("error", {"status": 500, "detail": UNAVAILABLE_DETAIL}))
        finally:
            reset_trace_id(token)
            await events.put(("done", {}))

    async def event_stream() -> AsyncIterator[str]:
        task = asyncio.create_task(run_chat())
        try:
            while True:
                event, data = await events.get()
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if event == "done":
                    break
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _search_pubmed_by_identifiers(
    provider: PubMedProvider,
    query: str,
) -> list[PubMedArticle]:
    """Recover cited evidence when the model tool loop returns no articles.

    The fallback is deliberately limited to explicit scientific/product
    identifiers from the user query.  It cannot broaden an arbitrary Chinese
    question into an unreviewed search query.
    """

    fallback_query = build_identifier_query(query)
    if fallback_query is None:
        return []
    try:
        with timed_stage(logger, "pubmed", tool="identifier_fallback"):
            articles = await provider.search_articles(
                fallback_query,
                max_results=provider.max_results,
            )
            if articles and any(not article.abstract for article in articles):
                articles = await provider.fetch_articles(
                    [article.pmid for article in articles]
                )
        return articles
    except PubMedProviderError as exc:
        logger.warning("PubMed identifier fallback failed: %s", type(exc).__name__)
        return []
