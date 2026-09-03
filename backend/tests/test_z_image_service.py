from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import Settings
from app.services.z_image_service import ZImageService, build_knowledge_image_prompt


def test_prompt_packages_question_and_answer_within_model_limit() -> None:
    prompt = build_knowledge_image_prompt("儿童为什么要接种疫苗？" * 80, "疫苗建立免疫记忆。" * 80)

    assert "儿童为什么要接种疫苗" in prompt
    assert "疫苗建立免疫记忆" in prompt
    assert "疫苗科普信息图" in prompt
    assert len(prompt) <= 800


@pytest.mark.asyncio
async def test_z_image_service_calls_dashscope_and_returns_image_url() -> None:
    response = SimpleNamespace(
        raise_for_status=Mock(),
        json=lambda: {
            "output": {
                "choices": [{"message": {"content": [{"image": "https://example.com/result.png"}]}}]
            }
        },
    )
    client = AsyncMock()
    client.post.return_value = response
    settings = Settings(dashscope_api_key="test-key")
    service = ZImageService(settings, client)

    image_url = await service.generate("疫苗如何发挥作用？", "疫苗帮助形成免疫记忆。")

    assert image_url == "https://example.com/result.png"
    call = client.post.await_args
    assert call.args[0] == settings.z_image_endpoint
    assert call.kwargs["json"]["model"] == "z-image-turbo"
    assert call.kwargs["json"]["parameters"]["size"] == "1024*1024"
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
