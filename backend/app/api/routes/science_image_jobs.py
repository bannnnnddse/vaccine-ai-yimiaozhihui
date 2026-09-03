"""REST endpoints for independent science-image generation jobs."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse

from app.schemas.image_pipeline import ImageEditRequest, ImageJobAccepted, ImageRestoreRequest
from app.schemas.knowledge_image import (
    ImageJobCreated,
    ImageJobCreateRequest,
    ImageJobStatus,
)
from app.services.image_roi_editor import InvalidBBoxError
from app.services.science_image_job_manager import (
    InvalidJobStateError,
    JobConflictError,
    JobNotFoundError,
    JobVersionConflictError,
    ScienceImageJobManager,
)

router = APIRouter(tags=["科学图解任务"])

UNAVAILABLE_DETAIL = "图解生成服务暂时不可用，请稍后重试。"

_SENSITIVE_TOKENS = ("sk-", "dashscope", "api_key", "api key", "bearer ")


def _sanitise_error_message(message: str) -> str:
    """Strip sensitive tokens and detect encoding corruption."""
    # Lone surrogates or replacement chars indicate a decode error upstream.
    if "�" in message or any("\ud800" <= c <= "\udfff" for c in message):
        return UNAVAILABLE_DETAIL
    lower = message.casefold()
    for token in _SENSITIVE_TOKENS:
        if token in lower:
            return UNAVAILABLE_DETAIL
    return message[:500]


def get_job_manager(request: Request) -> ScienceImageJobManager:
    return request.app.state.science_image_job_manager


# ── POST /image-jobs ───────────────────────────────────────────────


@router.post(
    "/image-jobs",
    response_model=ImageJobCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_image_job(
    payload: ImageJobCreateRequest,
    manager: Annotated[ScienceImageJobManager, Depends(get_job_manager)],
) -> ImageJobCreated:
    """Submit a new science-image generation job."""
    try:
        return await manager.create(payload.prompt)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except JobConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前已有正在生成的图解任务，请完成或取消后再提交。",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_sanitise_error_message(str(exc)),
        ) from exc


# ── GET /image-jobs/{job_id} ────────────────────────────────────────


@router.get("/image-jobs/{job_id}", response_model=ImageJobStatus)
async def get_image_job(
    job_id: str,
    manager: Annotated[ScienceImageJobManager, Depends(get_job_manager)],
) -> ImageJobStatus:
    """Query the stage and status of a science-image job."""
    result = await manager.get(job_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务未找到。",
        )
    return result


# ── DELETE /image-jobs/{job_id} ─────────────────────────────────────


@router.delete("/image-jobs/{job_id}")
async def cancel_image_job(
    job_id: str,
    manager: Annotated[ScienceImageJobManager, Depends(get_job_manager)],
) -> JSONResponse:
    """Cancel a running or queued science-image job."""
    cancelled = await manager.cancel(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在或已完成，无法取消。",
        )
    return JSONResponse(
        content={"detail": "任务已取消。"},
        status_code=status.HTTP_200_OK,
    )


# ── POST /image-jobs/{job_id}/retry ─────────────────────────────────


@router.post(
    "/image-jobs/{job_id}/retry",
    response_model=ImageJobCreated,
    status_code=status.HTTP_201_CREATED,
)
async def retry_image_job(
    job_id: str,
    manager: Annotated[ScienceImageJobManager, Depends(get_job_manager)],
) -> ImageJobCreated:
    """Retry a failed or cancelled job, reusing the scientific dossier."""
    try:
        try:
            result = await manager.retry(job_id)
        except JobConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="当前已有正在生成的图解任务，请完成或取消后再提交。",
            ) from exc

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="任务不可重试。只有失败或已取消且保留科学档案的任务才能重试。",
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_sanitise_error_message(str(exc)),
        ) from exc


@router.post(
    "/image-jobs/{job_id}/edits",
    response_model=ImageJobCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def edit_image_job(
    job_id: str,
    payload: ImageEditRequest,
    manager: Annotated[ScienceImageJobManager, Depends(get_job_manager)],
) -> ImageJobCreated:
    """Start one authoritative human bbox revision against the trusted version."""
    try:
        return await manager.edit(job_id, payload)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务未找到。") from exc
    except JobVersionConflictError as exc:
        raise HTTPException(
            status_code=409, detail="图片版本已更新，请基于最新结果重新编辑。"
        ) from exc
    except InvalidBBoxError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (JobConflictError, InvalidJobStateError) as exc:
        raise HTTPException(status_code=409, detail="当前任务状态不允许提交编辑。") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_sanitise_error_message(str(exc))) from exc


@router.post("/image-jobs/{job_id}/accept", response_model=ImageJobAccepted)
async def accept_image_job(
    job_id: str,
    manager: Annotated[ScienceImageJobManager, Depends(get_job_manager)],
) -> ImageJobAccepted:
    """Accept the current trusted image without promoting a rejected candidate."""
    try:
        await manager.accept(job_id)
        return ImageJobAccepted(job_id=job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务未找到。") from exc
    except (JobConflictError, InvalidJobStateError) as exc:
        raise HTTPException(status_code=409, detail="当前任务状态不允许接受结果。") from exc


@router.post("/image-jobs/{job_id}/restore-previous", response_model=ImageJobStatus)
async def restore_previous_image_job(
    job_id: str,
    payload: ImageRestoreRequest,
    manager: Annotated[ScienceImageJobManager, Depends(get_job_manager)],
) -> ImageJobStatus:
    """Switch the presented image back to its immediately preceding version."""
    try:
        return await manager.restore_previous(job_id, payload)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务未找到。") from exc
    except JobVersionConflictError as exc:
        raise HTTPException(status_code=409, detail="图片版本已更新，请刷新后重试。") from exc
    except (JobConflictError, InvalidJobStateError) as exc:
        raise HTTPException(status_code=409, detail="当前没有可恢复的上一版本。") from exc


# ── GET /generated-images/{filename} ────────────────────────────────


def _safe_image_path(filename: str, base_dir: Path) -> Path:
    """Resolve *filename* and verify it lives inside *base_dir*.

    Uses :meth:`Path.relative_to` so boundary checks cannot be bypassed
    by crafted strings.
    """
    candidate = (base_dir / filename).resolve()
    try:
        candidate.relative_to(base_dir.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="图片未找到。",
        ) from exc
    if not candidate.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="图片未找到。",
        )
    return candidate


@router.get("/generated-images/{filename}")
async def get_generated_image(request: Request, filename: str) -> FileResponse:
    """Serve a previously generated science image by filename."""
    settings = request.app.state.settings
    path = _safe_image_path(filename, settings.generated_image_dir)
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
