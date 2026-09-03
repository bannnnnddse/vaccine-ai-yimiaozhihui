from fastapi import APIRouter, Request

router = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health(request: Request) -> dict[str, str | bool]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "service": settings.app_name,
        "model": settings.qwen_model,
        "pubmed_enabled": settings.pubmed_enabled,
        "pubmed_provider_ready": request.app.state.pubmed_provider is not None,
        "knowledge_gap_capture_enabled": settings.pubmed_create_knowledge_gap,
    }
