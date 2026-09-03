import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.routes.knowledge_image import get_z_image_service, run_until_disconnect
from app.core.config import Settings
from app.main import create_app


def test_knowledge_image_returns_generated_url() -> None:
    app = create_app(Settings(dashscope_api_key=None))
    service = AsyncMock()
    service.generate.return_value = "https://example.com/vaccine.png"
    app.dependency_overrides[get_z_image_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/knowledge-image",
            json={"question": "疫苗如何发挥作用？", "answer": "疫苗帮助建立免疫记忆。"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "image_url": "https://example.com/vaccine.png",
        "model": "z-image-turbo",
    }
    service.generate.assert_awaited_once_with("疫苗如何发挥作用？", "疫苗帮助建立免疫记忆。")


@pytest.mark.asyncio
async def test_disconnect_cancels_running_generation() -> None:
    request = AsyncMock()
    request.is_disconnected.side_effect = [False, True]
    cancelled = asyncio.Event()

    async def slow_generation() -> str:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(asyncio.CancelledError):
        await run_until_disconnect(request, slow_generation(), poll_interval=0)

    assert cancelled.is_set()
