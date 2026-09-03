from typing import Any

import httpx

from app.core.config import Settings


def build_knowledge_image_prompt(question: str, answer: str) -> str:
    clean_question = " ".join(question.split())[:160]
    clean_answer = " ".join(answer.split())[:380]
    prompt = f"""生成一张面向中国家长和儿童的1:1疫苗科普信息图，主题明确、科学准确、温和可信。
主题问题：{clean_question}
科学回答：{clean_answer}
视觉要求：白色背景，医疗蓝和湖蓝为主色，少量绿色与橙色强调；采用清晰的二维医学科普插画和从左到右或环形流程；用3至5个简洁步骤表达核心机制；中文标题醒目，正文只保留必要短句，字号大且清晰；避免密集小字、写实针头恐吓、复杂背景、品牌标志、水印和夸大疗效；所有细胞、抗体和接种场景符合基础免疫学常识。"""
    return prompt[:800]


class ZImageServiceError(Exception):
    pass


class ZImageNotConfiguredError(ZImageServiceError):
    pass


class ZImageTimeoutError(ZImageServiceError):
    pass


class ZImageService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None) -> None:
        self._settings = settings
        self._client = client

    async def generate(self, question: str, answer: str) -> str:
        if self._client is None or not self._settings.dashscope_api_key:
            raise ZImageNotConfiguredError

        payload = {
            "model": self._settings.z_image_model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": build_knowledge_image_prompt(question, answer)}],
                    }
                ]
            },
            "parameters": {
                "prompt_extend": False,
                "size": self._settings.z_image_size,
            },
        }

        try:
            response = await self._client.post(
                self._settings.z_image_endpoint,
                headers={
                    "Authorization": f"Bearer {self._settings.dashscope_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            content = data["output"]["choices"][0]["message"]["content"]
            image_url = next(item["image"] for item in content if "image" in item)
        except httpx.TimeoutException as exc:
            raise ZImageTimeoutError from exc
        except (httpx.HTTPError, KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
            raise ZImageServiceError from exc

        if not isinstance(image_url, str) or not image_url.startswith("https://"):
            raise ZImageServiceError
        return image_url
