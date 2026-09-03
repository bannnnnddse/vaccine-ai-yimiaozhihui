import hmac
from collections.abc import Coroutine
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import FileResponse

from app.admin.auth import (
    ADMIN_COOKIE_NAME,
    AdminAuthError,
    AdminSession,
    create_admin_session,
    parse_admin_session,
    verify_admin_password,
)
from app.knowledge_gap.repository import KnowledgeGapConflictError, KnowledgeGapNotFoundError
from app.schemas.admin import (
    AdminLoginRequest,
    AdminSessionResponse,
    ApproveRequest,
    DecisionRequest,
    DraftResponse,
    GraphJobResponse,
    GraphRebuildRequest,
    KnowledgeGapDetailResponse,
    KnowledgeGapFilterStatus,
    KnowledgeGapListResponse,
    PublishRequest,
    ReviewUpdateRequest,
)
from app.services.knowledge_gap_review_service import (
    KnowledgeGapPublishError,
    KnowledgeGapReviewError,
    KnowledgeGapReviewService,
)

router = APIRouter(prefix="/admin", tags=["KnowledgeGap 管理"])


def get_review_service(request: Request) -> KnowledgeGapReviewService:
    return request.app.state.knowledge_gap_review_service


def require_admin_session(
    request: Request,
    token: Annotated[str | None, Cookie(alias=ADMIN_COOKIE_NAME)] = None,
) -> AdminSession:
    try:
        return parse_admin_session(request.app.state.settings, token)
    except AdminAuthError as exc:
        code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if not request.app.state.settings.admin_username
            else status.HTTP_401_UNAUTHORIZED
        )
        raise HTTPException(code, "管理会话不可用。") from exc


def require_admin_write(
    session: Annotated[AdminSession, Depends(require_admin_session)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AdminSession:
    if not csrf_token or not hmac.compare_digest(csrf_token, session.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "管理请求校验失败。")
    return session


@router.post("/session", response_model=AdminSessionResponse)
async def login(
    payload: AdminLoginRequest, request: Request, response: Response
) -> AdminSessionResponse:
    settings = request.app.state.settings
    try:
        valid = verify_admin_password(settings, payload.username, payload.password)
    except AdminAuthError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "管理员登录尚未配置。") from exc
    if not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误。")
    token, session = create_admin_session(settings)
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        token,
        max_age=settings.admin_session_ttl_seconds,
        httponly=True,
        secure=settings.admin_cookie_secure,
        samesite="strict",
        path="/api/v1/admin",
    )
    return AdminSessionResponse(
        username=session.username, csrf_token=session.csrf_token, expires_at=session.expires_at
    )


@router.get("/session", response_model=AdminSessionResponse)
async def get_session(
    session: Annotated[AdminSession, Depends(require_admin_session)],
) -> AdminSessionResponse:
    return AdminSessionResponse(
        username=session.username, csrf_token=session.csrf_token, expires_at=session.expires_at
    )


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    _session: Annotated[AdminSession, Depends(require_admin_write)],
) -> None:
    response.delete_cookie(ADMIN_COOKIE_NAME, path="/api/v1/admin")


@router.get("/knowledge-gaps", response_model=KnowledgeGapListResponse)
async def list_gaps(
    service: Annotated[KnowledgeGapReviewService, Depends(get_review_service)],
    _session: Annotated[AdminSession, Depends(require_admin_session)],
    gap_status: Annotated[KnowledgeGapFilterStatus | None, Query(alias="status")] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KnowledgeGapListResponse:
    items, total = await service.repository.list(
        status=gap_status, query=query, limit=limit, offset=offset
    )
    return KnowledgeGapListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/knowledge-gaps/{gap_id}", response_model=KnowledgeGapDetailResponse)
async def get_gap(
    gap_id: str,
    service: Annotated[KnowledgeGapReviewService, Depends(get_review_service)],
    _session: Annotated[AdminSession, Depends(require_admin_session)],
) -> KnowledgeGapDetailResponse:
    try:
        gap = await service.repository.get(gap_id)
        events = await service.repository.audit_events(gap_id)
        return KnowledgeGapDetailResponse(gap=gap, audit_events=events)
    except KnowledgeGapNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "KnowledgeGap 不存在。") from exc


@router.put("/knowledge-gaps/{gap_id}/review", response_model=KnowledgeGapDetailResponse)
async def save_review(
    gap_id: str,
    payload: ReviewUpdateRequest,
    service: Annotated[KnowledgeGapReviewService, Depends(get_review_service)],
    session: Annotated[AdminSession, Depends(require_admin_write)],
) -> KnowledgeGapDetailResponse:
    return await _mutate(service, gap_id, service.save_review(
        gap_id, version=payload.version, reviewer_note=payload.reviewer_note,
        candidate_claims=payload.candidate_claims, actor=session.username,
    ))


@router.post("/knowledge-gaps/{gap_id}/hold", response_model=KnowledgeGapDetailResponse)
async def hold_gap(
    gap_id: str, payload: DecisionRequest,
    service: Annotated[KnowledgeGapReviewService, Depends(get_review_service)],
    session: Annotated[AdminSession, Depends(require_admin_write)],
) -> KnowledgeGapDetailResponse:
    return await _mutate(service, gap_id, service.hold(
        gap_id, version=payload.version, reviewer_note=payload.reviewer_note, actor=session.username
    ))


@router.post("/knowledge-gaps/{gap_id}/reject", response_model=KnowledgeGapDetailResponse)
async def reject_gap(
    gap_id: str, payload: DecisionRequest,
    service: Annotated[KnowledgeGapReviewService, Depends(get_review_service)],
    session: Annotated[AdminSession, Depends(require_admin_write)],
) -> KnowledgeGapDetailResponse:
    return await _mutate(service, gap_id, service.reject(
        gap_id, version=payload.version, reviewer_note=payload.reviewer_note, actor=session.username
    ))


@router.post("/knowledge-gaps/{gap_id}/approve", response_model=KnowledgeGapDetailResponse)
async def approve_gap(
    gap_id: str, payload: ApproveRequest,
    service: Annotated[KnowledgeGapReviewService, Depends(get_review_service)],
    session: Annotated[AdminSession, Depends(require_admin_write)],
) -> KnowledgeGapDetailResponse:
    return await _mutate(service, gap_id, service.approve(
        gap_id, version=payload.version, title=payload.title,
        reviewer_note=payload.reviewer_note, candidate_claims=payload.candidate_claims,
        actor=session.username,
    ))


@router.get("/knowledge-gaps/{gap_id}/draft", response_model=DraftResponse)
async def preview_draft(
    gap_id: str,
    service: Annotated[KnowledgeGapReviewService, Depends(get_review_service)],
    _session: Annotated[AdminSession, Depends(require_admin_session)],
) -> DraftResponse:
    try:
        gap, content = await service.read_draft(gap_id)
        return DraftResponse(
            content=content,
            sha256=gap.draft_sha256 or "",
            generated_at=gap.draft_generated_at,
        )
    except (KnowledgeGapNotFoundError, KnowledgeGapReviewError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "审核草稿不可用。") from exc


@router.get("/knowledge-gaps/{gap_id}/draft/download")
async def download_draft(
    gap_id: str,
    service: Annotated[KnowledgeGapReviewService, Depends(get_review_service)],
    _session: Annotated[AdminSession, Depends(require_admin_session)],
) -> FileResponse:
    try:
        gap, _content = await service.read_draft(gap_id)
        path = service.draft_path(gap)
        return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)
    except (KnowledgeGapNotFoundError, KnowledgeGapReviewError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "审核草稿不可用。") from exc


@router.post(
    "/knowledge-gaps/{gap_id}/publish",
    response_model=GraphJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def publish_gap(
    gap_id: str, payload: PublishRequest, request: Request,
    service: Annotated[KnowledgeGapReviewService, Depends(get_review_service)],
    session: Annotated[AdminSession, Depends(require_admin_write)],
) -> GraphJobResponse:
    try:
        job = await service.queue_publish(
            gap_id,
            version=payload.version,
            actor=session.username,
            jobs=request.app.state.graph_job_repository,
        )
        return _job_response(job)
    except KnowledgeGapNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "KnowledgeGap 不存在。") from exc
    except KnowledgeGapConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "审核记录已发生变化，请刷新后重试。") from exc
    except KnowledgeGapReviewError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post(
    "/knowledge-graph/rebuild",
    response_model=GraphJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rebuild_graph(
    payload: GraphRebuildRequest,
    request: Request,
    _session: Annotated[AdminSession, Depends(require_admin_write)],
) -> GraphJobResponse:
    pointer = request.app.state.settings.rag_index_dir / "active.json"
    pointer_stamp = pointer.stat().st_mtime_ns if pointer.exists() else 0
    signature = f"rebuild:{payload.mode}:{payload.force_reextract}:{pointer_stamp}"
    job = await request.app.state.graph_job_repository.enqueue(
        "rebuild",
        payload.model_dump(),
        signature=signature,
    )
    return _job_response(job)


@router.get("/knowledge-graph/jobs/{task_id}", response_model=GraphJobResponse)
async def graph_job(
    task_id: str,
    request: Request,
    _session: Annotated[AdminSession, Depends(require_admin_session)],
) -> GraphJobResponse:
    job = await request.app.state.graph_job_repository.get(task_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图谱任务不存在。")
    return _job_response(job)


def _job_response(job) -> GraphJobResponse:
    return GraphJobResponse(
        task_id=job.id,
        status=job.status,
        kind=job.kind,
        stage=job.stage,
        progress=job.progress,
        processed_chunks=job.processed_chunks,
        total_chunks=job.total_chunks,
        result_graph_version=job.result_graph_version,
        result_index_version=job.result_index_version,
        error=job.error,
    )


async def _mutate(
    service: KnowledgeGapReviewService,
    gap_id: str,
    operation: Coroutine[Any, Any, Any],
) -> KnowledgeGapDetailResponse:
    try:
        gap = await operation
        return KnowledgeGapDetailResponse(
            gap=gap, audit_events=await service.repository.audit_events(gap_id)
        )
    except KnowledgeGapNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "KnowledgeGap 不存在。") from exc
    except KnowledgeGapConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "审核记录已发生变化，请刷新后重试。") from exc
    except KnowledgeGapPublishError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "知识发布失败，原审核状态已保留。",
        ) from exc
    except KnowledgeGapReviewError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
