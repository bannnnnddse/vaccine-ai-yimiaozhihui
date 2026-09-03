from types import SimpleNamespace

import pytest

from app.services.wan_api_client import WanApiClient


def test_http_400_includes_safe_provider_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    client = WanApiClient(
        api_key="secret-key",
        api_base="https://dashscope.example/api/v1",
        timeout_seconds=10,
    )
    response = SimpleNamespace(
        status_code=400,
        json=lambda: {
            "code": "InvalidParameter",
            "message": "Input image width and height must both be at least 240 pixels.",
            "request_id": "req-123",
        },
    )
    monkeypatch.setattr(client._session, "request", lambda *args, **kwargs: response)

    with pytest.raises(RuntimeError) as caught:
        client._request_json({"input": "not-echoed"}, endpoint="https://dashscope.example/edit")

    message = str(caught.value)
    assert "HTTP 400" in message
    assert "code=InvalidParameter" in message
    assert "at least 240 pixels" in message
    assert "request_id=req-123" in message
    assert "not-echoed" not in message
    assert "secret-key" not in message
