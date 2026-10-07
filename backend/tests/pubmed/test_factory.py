import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.pubmed.direct_provider import DirectPubMedProvider
from app.pubmed.factory import create_pubmed_provider
from app.pubmed.mcp_provider import MCPPubMedProvider
from app.pubmed.provider import PubMedUnavailableError


def test_disabled_pubmed_does_not_create_external_provider() -> None:
    assert create_pubmed_provider(Settings(pubmed_enabled=False)) is None


def test_mcp_settings_create_mcp_adapter() -> None:
    provider = create_pubmed_provider(
        Settings(pubmed_enabled=True, pubmed_provider="mcp", pubmed_mcp_url="https://example.test/mcp")
    )

    assert isinstance(provider, MCPPubMedProvider)


def test_direct_provider_requires_explicit_http_client() -> None:
    with pytest.raises(PubMedUnavailableError, match="HTTP client"):
        create_pubmed_provider(Settings(pubmed_enabled=True, pubmed_provider="direct"))


@pytest.mark.asyncio
async def test_direct_settings_create_direct_adapter() -> None:
    async with httpx.AsyncClient() as client:
        provider = create_pubmed_provider(
            Settings(pubmed_enabled=True, pubmed_provider="direct"),
            client,
        )
        assert isinstance(provider, DirectPubMedProvider)
        assert provider._client is client


def test_default_direct_lifespan_reuses_client_and_closes_it(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            dashscope_api_key=None,
            pubmed_enabled=True,
            app_database_path=tmp_path / "app.db",
            knowledge_draft_dir=tmp_path / "drafts",
        )
    )
    with TestClient(app) as client:
        provider = app.state.pubmed_provider
        assert isinstance(provider, DirectPubMedProvider)
        shared_client = provider._client
        assert shared_client.timeout == httpx.Timeout(None)
        assert shared_client.is_closed is False
        assert app.state.pubmed_provider._client is shared_client
        assert client.get("/api/v1/health").json()["pubmed_provider_ready"] is True
    assert shared_client.is_closed is True
