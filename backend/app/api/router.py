from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge_graph import router as knowledge_graph_router
from app.api.routes.knowledge_image import router as knowledge_image_router
from app.api.routes.science_image_jobs import router as science_image_jobs_router

api_router = APIRouter()
api_router.include_router(admin_router)
api_router.include_router(health_router)
api_router.include_router(chat_router)
api_router.include_router(knowledge_image_router)
api_router.include_router(knowledge_graph_router)
api_router.include_router(science_image_jobs_router)
