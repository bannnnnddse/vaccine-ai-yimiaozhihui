from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_returns_service_status_without_calling_ai() -> None:
    app = create_app(
        Settings(
            dashscope_api_key=None,
            pubmed_enabled=False,
            pubmed_create_knowledge_gap=False,
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "vaccine-ai-backend",
        "model": "qwen3.8-flash",
        "pubmed_enabled": False,
        "pubmed_provider_ready": False,
        "knowledge_gap_capture_enabled": False,
    }
