import httpx
import pytest

from app.core.config import Settings
from app.pubmed.direct_provider import DirectPubMedProvider
from app.pubmed.factory import create_pubmed_provider
from app.pubmed.mcp_provider import MCPPubMedProvider
from app.pubmed.provider import PubMedUnavailableError


def test_disabled_pubmed_does_not_create_external_provider() -> None:
    assert create_pubmed_provider(Settings(pubmed_enabled=False)) is None


def test_mcp_settings_create_mcp_adapter() -> None:
    provider = create_pubmed_provider(
        Settings(pubmed_enabled=True, pubmed_mcp_url="https://example.test/mcp")
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
