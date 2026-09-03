import httpx

from app.core.config import Settings
from app.pubmed.direct_provider import DirectPubMedProvider
from app.pubmed.mcp_provider import MCPPubMedProvider
from app.pubmed.provider import PubMedProvider, PubMedUnavailableError


def create_pubmed_provider(
    settings: Settings,
    direct_http_client: httpx.AsyncClient | None = None,
) -> PubMedProvider | None:
    if not settings.pubmed_enabled:
        return None
    if settings.pubmed_provider == "mcp":
        if settings.pubmed_mcp_url is None:  # guarded by Settings validation
            raise PubMedUnavailableError("PubMed MCP URL is not configured")
        return MCPPubMedProvider.from_url(
            settings.pubmed_mcp_url,
            timeout_seconds=settings.pubmed_timeout_seconds,
            retries=settings.pubmed_mcp_retries,
            max_results=settings.pubmed_max_results,
            max_query_length=settings.pubmed_max_query_length,
            proxy_url=settings.pubmed_proxy_url,
        )
    if direct_http_client is None:
        raise PubMedUnavailableError("Direct PubMed HTTP client is not configured")
    return DirectPubMedProvider(
        direct_http_client,
        api_key=settings.ncbi_api_key,
        email=settings.ncbi_email,
        tool=settings.ncbi_tool,
        timeout_seconds=settings.pubmed_timeout_seconds,
        retries=settings.pubmed_direct_retries,
        max_results=settings.pubmed_max_results,
        max_query_length=settings.pubmed_max_query_length,
    )
