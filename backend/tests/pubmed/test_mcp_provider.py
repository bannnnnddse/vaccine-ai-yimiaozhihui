from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.pubmed.mcp_provider import FETCH_TOOL, SEARCH_TOOL, MCPPubMedProvider
from app.pubmed.provider import (
    PubMedMalformedResponseError,
    PubMedRateLimitError,
    PubMedTimeoutError,
    PubMedUnavailableError,
)


def _result(structured: object, *, is_error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        structuredContent=structured,
        isError=is_error,
        content=[SimpleNamespace(text=str(structured))],
    )


@pytest.mark.asyncio
async def test_search_maps_cyanheads_summaries_to_articles() -> None:
    client = AsyncMock()
    client.call_tool.return_value = _result(
        {
            "pmids": ["123", "456"],
            "summaries": [
                {
                    "pmid": "123",
                    "title": "HPV vaccine safety",
                    "authors": "Alice Smith, Bob Li",
                    "source": "Vaccine",
                    "pubDate": "2025 Jan",
                    "doi": "10.1/example",
                    "pubmedUrl": "https://pubmed.ncbi.nlm.nih.gov/123/",
                }
            ],
        }
    )
    provider = MCPPubMedProvider(client, retries=0)

    articles = await provider.search_articles("HPV vaccine safety", max_results=2)

    assert [article.pmid for article in articles] == ["123", "456"]
    assert articles[0].authors == ["Alice Smith", "Bob Li"]
    assert articles[0].publication_year == 2025
    assert articles[1].title == "PubMed article PMID 456"
    name, arguments = client.call_tool.await_args.args
    assert name == SEARCH_TOOL
    assert arguments["maxResults"] == 2
    assert arguments["summaryCount"] == 2


@pytest.mark.asyncio
async def test_fetch_maps_abstract_authors_journal_and_types() -> None:
    client = AsyncMock()
    client.call_tool.return_value = _result(
        {
            "articles": [
                {
                    "pmid": "123",
                    "title": "A randomized trial",
                    "abstractText": "Structured evidence.",
                    "authors": [
                        {"firstName": "Alice", "lastName": "Smith"},
                        {"collectiveName": "Study Group"},
                    ],
                    "journalInfo": {
                        "title": "Vaccine",
                        "publicationDate": {"year": "2024"},
                    },
                    "doi": "10.1/trial",
                    "publicationTypes": ["Randomized Controlled Trial"],
                    "pubmedUrl": "https://pubmed.ncbi.nlm.nih.gov/123/",
                }
            ]
        }
    )
    provider = MCPPubMedProvider(client, retries=0)

    articles = await provider.fetch_articles(["123"])

    assert len(articles) == 1
    assert articles[0].abstract == "Structured evidence."
    assert articles[0].authors == ["Alice Smith", "Study Group"]
    assert articles[0].journal == "Vaccine"
    assert articles[0].publication_types == ["Randomized Controlled Trial"]
    assert client.call_tool.await_args.args[0] == FETCH_TOOL


@pytest.mark.asyncio
async def test_empty_search_results_are_valid() -> None:
    client = AsyncMock()
    client.call_tool.return_value = _result({"pmids": [], "summaries": []})
    provider = MCPPubMedProvider(client, retries=0)

    assert await provider.search_articles("no matching vaccine") == []


@pytest.mark.asyncio
async def test_timeout_is_retried_then_mapped() -> None:
    client = AsyncMock()
    client.call_tool.side_effect = TimeoutError
    provider = MCPPubMedProvider(client, timeout_seconds=0.1, retries=1)

    with pytest.raises(PubMedTimeoutError):
        await provider.search_articles("vaccines")
    assert client.call_tool.await_count == 2


@pytest.mark.asyncio
async def test_malformed_structured_content_is_not_retried() -> None:
    client = AsyncMock()
    client.call_tool.return_value = _result({"pmids": "not-a-list", "summaries": []})
    provider = MCPPubMedProvider(client, retries=2)

    with pytest.raises(PubMedMalformedResponseError):
        await provider.search_articles("vaccines")
    assert client.call_tool.await_count == 1


@pytest.mark.asyncio
async def test_rate_limit_error_is_structured_and_retried() -> None:
    client = AsyncMock()
    client.call_tool.return_value = _result("429 rate limit", is_error=True)
    provider = MCPPubMedProvider(client, retries=1)

    with pytest.raises(PubMedRateLimitError):
        await provider.search_articles("vaccines")
    assert client.call_tool.await_count == 2


@pytest.mark.asyncio
async def test_mcp_unavailable_is_structured_and_retried() -> None:
    client = AsyncMock()
    client.call_tool.side_effect = ConnectionError("connection refused")
    provider = MCPPubMedProvider(client, retries=1)

    with pytest.raises(PubMedUnavailableError):
        await provider.search_articles("vaccines")
    assert client.call_tool.await_count == 2
