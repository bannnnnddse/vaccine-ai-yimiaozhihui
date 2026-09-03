"""Small, owned DashScope WAN HTTP client used by the image-job pipeline."""

from __future__ import annotations

import base64
import io
import re
import time
from typing import Any

import requests
from PIL import Image, UnidentifiedImageError


def _safe_provider_error_details(data: object) -> str:
    """Extract bounded diagnostic fields without echoing request payloads or headers."""

    if not isinstance(data, dict):
        return ""
    parts: list[str] = []
    code = data.get("code")
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code):
        parts.append(f"code={code}")
    message = data.get("message")
    if isinstance(message, str):
        message = " ".join(message.split())[:300]
        if message:
            parts.append(f"message={message}")
    request_id = data.get("request_id") or data.get("requestId")
    if isinstance(request_id, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request_id):
        parts.append(f"request_id={request_id}")
    return " ".join(parts)


class WanApiClient:
    """Submit, poll, and download WAN images without a legacy generator package."""

    def __init__(self, *, api_key: str, api_base: str, timeout_seconds: float) -> None:
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        # Host proxy settings are not part of the application contract.
        self._session.trust_env = False

    def generate(
        self,
        *,
        prompt: str,
        reference_images: list[bytes],
        model: str,
        aspect_ratio: str,
        image_size: str,
    ) -> bytes:
        if model not in {"wan2.7-image", "wan2.7-image-pro"}:
            raise ValueError("unsupported WAN image model")
        content = [self._encode_reference_image(value) for value in reference_images]
        content.append({"text": prompt})
        parameters: dict[str, Any] = {"n": 1, "watermark": False, "size": image_size}
        if not reference_images:
            parameters["thinking_mode"] = True
        payload = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }
        response = self._request_json(
            payload,
            endpoint=f"{self._api_base}/services/aigc/image-generation/generation",
            extra_headers={"X-DashScope-Async": "enable"},
        )
        output = response.get("output")
        task_id = output.get("task_id") if isinstance(output, dict) else None
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
            raise RuntimeError("WAN submit response missing a valid task ID")
        return self._poll(task_id)

    def _poll(self, task_id: str) -> bytes:
        deadline = time.monotonic() + self._timeout_seconds
        endpoint = f"{self._api_base}/tasks/{task_id}"
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("WAN image task timed out while polling")
            time.sleep(min(2, remaining))
            response = self._get_json(endpoint, timeout=remaining)
            output = response.get("output")
            status = output.get("task_status") if isinstance(output, dict) else None
            if status in {"PENDING", "RUNNING", "UNKNOWN"}:
                continue
            if status == "SUCCEEDED":
                return self._download_image(self._find_image_url(response))
            if status in {"FAILED", "CANCELED"}:
                code = output.get("code") if isinstance(output, dict) else None
                valid_code = isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", code)
                suffix = f" (code: {code})" if valid_code else ""
                raise RuntimeError(f"WAN image task {status}{suffix}")
            raise RuntimeError("WAN poll response had an invalid task status")

    @staticmethod
    def _encode_reference_image(image_bytes: bytes) -> dict[str, str]:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
                image_format = image.format
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("reference image must be valid PNG, JPEG, or WEBP bytes") from exc
        mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(
            image_format or ""
        )
        if mime is None:
            raise ValueError("reference image must be valid PNG, JPEG, or WEBP bytes")
        return {"image": f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"}

    def _request_json(
        self,
        payload: dict[str, Any],
        *,
        endpoint: str,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        return self._request("POST", endpoint, headers=headers, json=payload)

    def _get_json(self, endpoint: str, *, timeout: float) -> dict[str, Any]:
        return self._request(
            "GET",
            endpoint,
            headers={"Authorization": f"Bearer {self._api_key}"},
            request_timeout=timeout,
        )

    def _request(
        self, method: str, endpoint: str, *, request_timeout: float | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        for attempt in range(3):
            try:
                response = self._session.request(
                    method, endpoint, timeout=request_timeout or self._timeout_seconds, **kwargs
                )
            except requests.RequestException:
                if attempt == 2:
                    raise RuntimeError("WAN request failed after retries") from None
                time.sleep(2**attempt)
                continue
            try:
                data = response.json()
            except ValueError:
                data = None
            if 200 <= response.status_code < 300 and isinstance(data, dict):
                return data
            if response.status_code in {401, 403}:
                raise RuntimeError("WAN authentication failed")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
            details = _safe_provider_error_details(data)
            suffix = f": {details}" if details else ""
            raise RuntimeError(f"WAN request failed (HTTP {response.status_code}){suffix}")
        raise RuntimeError("WAN request failed after retries")

    @staticmethod
    def _find_image_url(response: dict[str, Any]) -> str:
        choices = response.get("output", {}).get("choices", [])
        if isinstance(choices, list):
            for choice in choices:
                content = (
                    choice.get("message", {}).get("content", [])
                    if isinstance(choice, dict)
                    else []
                )
                if isinstance(content, list):
                    for part in content:
                        value = part.get("image") if isinstance(part, dict) else None
                        if isinstance(value, str) and value.strip():
                            return value
        raise RuntimeError("WAN response missing a generated image URL")

    def _download_image(self, image_url: str) -> bytes:
        for attempt in range(3):
            try:
                response = self._session.get(image_url, timeout=self._timeout_seconds)
            except requests.RequestException:
                if attempt == 2:
                    raise RuntimeError("generated image download failed after retries") from None
                time.sleep(2**attempt)
                continue
            if 200 <= response.status_code < 300:
                if not str(response.headers.get("Content-Type", "")).lower().startswith("image/"):
                    raise RuntimeError("generated image URL returned a non-image Content-Type")
                return response.content
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
            raise RuntimeError(f"generated image download failed (HTTP {response.status_code})")
        raise RuntimeError("generated image download failed after retries")
