import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from starlette.concurrency import run_in_threadpool

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.observability import reset_trace_id, set_trace_id, timed_stage
from app.graph.jobs import GraphJobRepository
from app.graph.public_store import PublicGraphStore
from app.graph.service import GraphService
from app.knowledge_gap.repository import SqliteKnowledgeGapRepository
from app.pubmed.factory import create_pubmed_provider
from app.rag.runtime import configure_cpu_threads
from app.rag.service import RagService
from app.services.edit_instruction_rewriter import EditInstructionRewriter
from app.services.edit_scope_guard_service import EditScopeGuardService
from app.services.evidence_assessment import EvidenceAssessmentService
from app.services.knowledge_gap_review_service import KnowledgeGapReviewService
from app.services.knowledge_gap_service import KnowledgeGapService
from app.services.qwen_service import QwenService
from app.services.science_image_job_manager import ScienceImageJobManager
from app.services.science_image_organizer import ScienceImageOrganizer
from app.services.visual_critic_service import VisualCriticService
from app.services.wan_image_generator import WanImageGenerator
from app.services.z_image_service import ZImageService

logger = logging.getLogger(__name__)


def configure_application_logging() -> None:
    """Emit application observability logs when Uvicorn owns logging setup.

    Uvicorn configures its own loggers but leaves the ``app`` namespace at the
    root logger's default WARNING level.  Production stage timings are INFO
    records, so give only our application namespace a stderr handler rather
    than raising the verbosity of every dependency.
    """
    application_logger = logging.getLogger("app")
    application_logger.setLevel(logging.INFO)
    if application_logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    application_logger.addHandler(handler)
    application_logger.propagate = False


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_application_logging()
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client: AsyncOpenAI | None = None
        image_client: httpx.AsyncClient | None = None
        pubmed_http_client: httpx.AsyncClient | None = None
        if app_settings.dashscope_api_key:
            model_http_client = httpx.AsyncClient(
                timeout=app_settings.qwen_timeout_seconds,
                trust_env=False,
            )
            client = AsyncOpenAI(
                api_key=app_settings.dashscope_api_key,
                base_url=app_settings.dashscope_base_url,
                timeout=app_settings.qwen_timeout_seconds,
                max_retries=0,
                http_client=model_http_client,
            )
            image_client = httpx.AsyncClient(
                timeout=app_settings.z_image_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
            )
        if (
            app_settings.rag_embedding_device.casefold() == "cpu"
            or app_settings.rag_reranker_device.casefold() == "cpu"
        ):
            configure_cpu_threads(
                app_settings.rag_torch_num_threads,
                app_settings.rag_torch_interop_threads,
            )
        qwen_service = QwenService(app_settings, client)
        app.state.qwen_service = qwen_service
        app.state.evidence_assessment_service = EvidenceAssessmentService(
            qwen_service,
            rule_min_top_score=app_settings.evidence_rule_min_top_score,
            rule_min_support_score=app_settings.evidence_rule_min_support_score,
        )
        rag_service = RagService.from_settings(app_settings)
        app.state.rag_service = rag_service
        app.state.rag_semaphore = asyncio.Semaphore(
            app_settings.rag_max_concurrent_retrievals
        )
        app.state.graph_service = GraphService.from_settings(app_settings)
        app.state.public_graph_store = PublicGraphStore(app_settings)
        app.state.graph_job_repository = GraphJobRepository(app_settings.app_database_path)
        if app_settings.pubmed_enabled and app_settings.pubmed_provider == "direct":
            pubmed_http_client = httpx.AsyncClient(
                timeout=app_settings.pubmed_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
                proxy=app_settings.pubmed_proxy_url,
            )
        app.state.pubmed_provider = create_pubmed_provider(app_settings, pubmed_http_client)
        knowledge_gap_repository = SqliteKnowledgeGapRepository(app_settings.app_database_path)
        app.state.knowledge_gap_service = (
            KnowledgeGapService(knowledge_gap_repository)
            if app_settings.pubmed_create_knowledge_gap
            else None
        )
        app.state.knowledge_gap_review_service = KnowledgeGapReviewService(
            app_settings, knowledge_gap_repository, app.state.rag_service
        )
        app.state.z_image_service = ZImageService(app_settings, image_client)
        organizer = ScienceImageOrganizer(app_settings, client)
        app.state.science_image_organizer = organizer
        wan_generator = WanImageGenerator(app_settings)
        app.state.wan_image_generator = wan_generator
        critic = VisualCriticService(app_settings, client)
        app.state.visual_critic_service = critic
        edit_rewriter = EditInstructionRewriter()
        guard = EditScopeGuardService(
            app_settings.image_edit_scope_guard_threshold,
            app_settings.image_edit_min_inside_change,
        )
        app.state.science_image_job_manager = ScienceImageJobManager(
            app_settings, organizer, wan_generator, critic, edit_rewriter, guard
        )
        try:
            if app_settings.rag_warmup_enabled:
                token = set_trace_id("startup-rag-warmup")
                try:
                    with timed_stage(logger, "rag_warmup"):
                        trace = await run_in_threadpool(rag_service.warmup)
                    logger.info(
                        "RAG warmup completed pipeline=%s timings_ms=%s",
                        trace.pipeline,
                        trace.timings_ms,
                    )
                finally:
                    reset_trace_id(token)
            yield
        finally:
            if client is not None:
                await client.close()
            if image_client is not None:
                await image_client.aclose()
            if pubmed_http_client is not None:
                await pubmed_http_client.aclose()

    app = FastAPI(
        title="疫苗知识 AI 后端",
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = app_settings

    @app.middleware("http")
    async def trace_requests(request, call_next):
        trace_id = uuid.uuid4().hex
        token = set_trace_id(trace_id)
        request.state.trace_id = trace_id
        try:
            if request.url.path == "/api/v1/chat":
                with timed_stage(
                    logger,
                    "chat_request",
                    method=request.method,
                    path=request.url.path,
                ):
                    response = await call_next(request)
            else:
                response = await call_next(request)
            response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            reset_trace_id(token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
