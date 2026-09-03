import asyncio
from collections.abc import Coroutine
from typing import Annotated, Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.knowledge_image import KnowledgeImageRequest, KnowledgeImageResponse
from app.services.z_image_service import (
    ZImageNotConfiguredError,
    ZImageService,
    ZImageServiceError,
    ZImageTimeoutError,
)

router = APIRouter(tags=["知识图解"])
UNAVAILABLE_DETAIL = "图解生成服务暂时不可用，请稍后重试。"
T = TypeVar("T")


def get_z_image_service(request: Request) -> ZImageService:
    return request.app.state.z_image_service


async def run_until_disconnect(
    request: Request,
    operation: Coroutine[Any, Any, T],
    poll_interval: float = 0.1,
) -> T:
    """Run an upstream request while the browser is still connected."""
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise asyncio.CancelledError
            await asyncio.sleep(poll_interval)
        return await task
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


@router.post("/knowledge-image", response_model=KnowledgeImageResponse)
async def generate_knowledge_image(
    payload: KnowledgeImageRequest,
    service: Annotated[ZImageService, Depends(get_z_image_service)],
    request: Request,
) -> KnowledgeImageResponse:
    try:
        image_url = await run_until_disconnect(
            request,
            service.generate(payload.question, payload.answer),
        )
    except ZImageNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UNAVAILABLE_DETAIL,
        ) from exc
    except ZImageTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=UNAVAILABLE_DETAIL,
        ) from exc
    except ZImageServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=UNAVAILABLE_DETAIL,
        ) from exc

    return KnowledgeImageResponse(
        image_url=image_url,
        model=request.app.state.settings.z_image_model,
    )
