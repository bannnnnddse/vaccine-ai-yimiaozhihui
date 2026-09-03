import httpx
import pytest

from app.pubmed.direct_provider import DirectPubMedProvider
from app.pubmed.provider import (
    PubMedMalformedResponseError,
    PubMedRateLimitError,
    PubMedTimeoutError,
    PubMedUnavailableError,
)

ARTICLE_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>123</PMID>
      <Article>
        <ArticleTitle>HPV <i>vaccine</i> safety study</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Background evidence.</AbstractText>
          <AbstractText Label="RESULTS">Safety results.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Smith</LastName><ForeName>Alice</ForeName></Author>
          <Author><CollectiveName>Study Group</CollectiveName></Author>
        </AuthorList>
        <Journal>
          <Title>Vaccine</Title>
          <JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue>
        </Journal>
        <PublicationTypeList>
          <PublicationType>Randomized Controlled Trial</PublicationType>
        </PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList><ArticleId IdType="doi">10.1/example</ArticleId></ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""


@pytest.mark.asyncio
async def test_search_runs_esearch_then_efetch_and_normalizes_articles() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["123"]}})
        return httpx.Response(200, content=ARTICLE_XML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DirectPubMedProvider(
            client,
            email="team@example.test",
            tool="vaccine-ai-backend",
            retries=0,
            request_interval_seconds=0,
        )
        articles = await provider.search_articles("HPV vaccine safety", max_results=1)

    assert len(requests) == 2
    assert requests[0].url.params["db"] == "pubmed"
    assert requests[0].url.params["tool"] == "vaccine-ai-backend"
    assert requests[0].url.params["email"] == "team@example.test"
    assert requests[1].url.params["id"] == "123"
    assert articles[0].title == "HPV vaccine safety study"
    assert articles[0].abstract == "BACKGROUND: Background evidence.\nRESULTS: Safety results."
    assert articles[0].authors == ["Alice Smith", "Study Group"]
    assert articles[0].publication_year == 2025
    assert articles[0].doi == "10.1/example"
    assert articles[0].publication_types == ["Randomized Controlled Trial"]


@pytest.mark.asyncio
async def test_search_empty_results_does_not_call_efetch() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"esearchresult": {"idlist": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DirectPubMedProvider(client, retries=0, request_interval_seconds=0)
        assert await provider.search_articles("no results") == []

    assert call_count == 1


@pytest.mark.asyncio
async def test_direct_provider_maps_timeout_and_retries() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DirectPubMedProvider(client, retries=1, request_interval_seconds=0)
        with pytest.raises(PubMedTimeoutError):
            await provider.search_articles("vaccines")

    assert call_count == 2


@pytest.mark.asyncio
async def test_direct_provider_maps_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DirectPubMedProvider(client, retries=0, request_interval_seconds=0)
        with pytest.raises(PubMedRateLimitError):
            await provider.search_articles("vaccines")


@pytest.mark.asyncio
async def test_direct_provider_maps_service_outage_and_retries() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DirectPubMedProvider(client, retries=1, request_interval_seconds=0)
        with pytest.raises(PubMedUnavailableError):
            await provider.search_articles("vaccines")

    assert call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"wrong": {}}),
    ],
)
async def test_direct_provider_rejects_malformed_search_response(
    response: httpx.Response,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DirectPubMedProvider(client, retries=0, request_interval_seconds=0)
        with pytest.raises(PubMedMalformedResponseError):
            await provider.search_articles("vaccines")


@pytest.mark.asyncio
async def test_direct_provider_rejects_malformed_fetch_xml() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<wrong />")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DirectPubMedProvider(client, retries=0, request_interval_seconds=0)
        with pytest.raises(PubMedMalformedResponseError):
            await provider.fetch_articles(["123"])
