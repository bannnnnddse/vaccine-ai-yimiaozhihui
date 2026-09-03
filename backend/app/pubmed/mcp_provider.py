import asyncio
import re
from collections.abc import Mapping
from typing import Any, Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import ValidationError

from app.pubmed.models import PubMedArticle
from app.pubmed.provider import (
    PubMedMalformedResponseError,
    PubMedProvider,
    PubMedProviderError,
    PubMedRateLimitError,
    PubMedTimeoutError,
    PubMedUnavailableError,
)

SEARCH_TOOL = "pubmed_search_articles"
FETCH_TOOL = "pubmed_fetch_articles"
RELATED_TOOL = "pubmed_find_related"


class MCPToolClient(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> object: ...


class StreamableHTTPMCPClient:
    def __init__(
        self,
        url: str,
        *,
        timeout_seconds: float,
        proxy_url: str | None = None,
    ) -> None:
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._proxy_url = proxy_url

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> object:
        timeout = httpx.Timeout(self._timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            trust_env=False,
            proxy=self._proxy_url,
        ) as client:
            async with streamable_http_client(self._url, http_client=client) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return await session.call_tool(name, arguments=arguments)


class MCPPubMedProvider(PubMedProvider):
    """Adapter for cyanheads/pubmed-mcp-server's minimal read-only tool subset."""

    def __init__(
        self,
        client: MCPToolClient,
        *,
        timeout_seconds: float = 20,
        retries: int = 1,
        max_results: int = 5,
        max_query_length: int = 500,
    ) -> None:
        super().__init__(max_results=max_results, max_query_length=max_query_length)
        if timeout_seconds <= 0:
            raise ValueError("PubMed MCP timeout must be positive")
        if not 0 <= retries <= 3:
            raise ValueError("PubMed MCP retries must be between 0 and 3")
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._retries = retries

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        timeout_seconds: float = 20,
        retries: int = 1,
        max_results: int = 5,
        max_query_length: int = 500,
        proxy_url: str | None = None,
    ) -> "MCPPubMedProvider":
        return cls(
            StreamableHTTPMCPClient(
                url,
                timeout_seconds=timeout_seconds,
                proxy_url=proxy_url,
            ),
            timeout_seconds=timeout_seconds,
            retries=retries,
            max_results=max_results,
            max_query_length=max_query_length,
        )

    async def _search_articles(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[PubMedArticle]:
        data = await self._call_tool(
            SEARCH_TOOL,
            {
                "query": query,
                "maxResults": max_results,
                "offset": 0,
                "sort": "relevance",
                "summaryCount": max_results,
            },
        )
        pmids = self._string_list(data.get("pmids"), field="pmids")[:max_results]
        summaries = data.get("summaries", [])
        if not isinstance(summaries, list):
            raise PubMedMalformedResponseError("MCP search summaries must be a list")
        summary_by_pmid = {
            str(item.get("pmid")): item
            for item in summaries
            if isinstance(item, Mapping) and item.get("pmid") is not None
        }
        articles: list[PubMedArticle] = []
        for pmid in pmids:
            summary = summary_by_pmid.get(pmid, {})
            authors = self._split_authors(summary.get("authors"))
            articles.append(
                self._article_from_mapping(
                    {
                        "pmid": pmid,
                        "title": summary.get("title") or f"PubMed article PMID {pmid}",
                        "authors": authors,
                        "journal": summary.get("source") or "",
                        "publication_year": self._extract_year(summary.get("pubDate")),
                        "doi": summary.get("doi"),
                        "url": summary.get("pubmedUrl"),
                    }
                )
            )
        return articles

    async def _fetch_articles(self, pmids: list[str]) -> list[PubMedArticle]:
        data = await self._call_tool(
            FETCH_TOOL,
            {"pmids": pmids, "includeMesh": True, "includeGrants": False},
        )
        raw_articles = data.get("articles", [])
        if not isinstance(raw_articles, list):
            raise PubMedMalformedResponseError("MCP fetch articles must be a list")
        return [
            self._article_from_mapping(self._normalize_fetched_article(item))
            for item in raw_articles[: self.max_results]
            if isinstance(item, Mapping)
        ]

    async def _find_related(
        self,
        pmid: str,
        *,
        max_results: int,
    ) -> list[PubMedArticle]:
        data = await self._call_tool(
            RELATED_TOOL,
            {
                "pmid": pmid,
                "relationship": "similar",
                "maxResults": max_results,
                "offset": 0,
            },
        )
        raw_articles = data.get("articles", [])
        if not isinstance(raw_articles, list):
            raise PubMedMalformedResponseError("MCP related articles must be a list")
        return [
            self._article_from_mapping(
                {
                    "pmid": item.get("pmid"),
                    "title": item.get("title") or f"PubMed article PMID {item.get('pmid')}",
                    "authors": self._split_authors(item.get("authors")),
                    "journal": item.get("source") or "",
                    "publication_year": self._extract_year(item.get("pubDate")),
                }
            )
            for item in raw_articles[:max_results]
            if isinstance(item, Mapping)
        ]

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        last_error: PubMedProviderError | None = None
        for attempt in range(self._retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._client.call_tool(name, arguments),
                    timeout=self._timeout_seconds,
                )
                data = self._extract_structured_content(result)
                return data
            except TimeoutError as exc:
                last_error = PubMedTimeoutError("PubMed MCP request timed out")
                last_error.__cause__ = exc
            except PubMedRateLimitError as exc:
                last_error = exc
            except PubMedMalformedResponseError:
                raise
            except PubMedProviderError as exc:
                last_error = exc
            except Exception as exc:
                last_error = self._map_external_error(exc)
            if attempt < self._retries:
                await asyncio.sleep(0)
        if last_error is None:  # pragma: no cover - loop always executes
            raise PubMedUnavailableError("PubMed MCP request failed")
        raise last_error

    @classmethod
    def _extract_structured_content(cls, result: object) -> dict[str, Any]:
        is_error = getattr(result, "isError", False)
        if is_error:
            text = cls._content_text(result)
            raise cls._error_from_text(text)
        structured = getattr(result, "structuredContent", None)
        if structured is None and isinstance(result, Mapping):
            if result.get("isError"):
                raise cls._error_from_text(str(result.get("content", "")))
            structured = result.get("structuredContent", result.get("structured_content"))
        if not isinstance(structured, Mapping):
            raise PubMedMalformedResponseError("MCP result has no structured content")
        return dict(structured)

    @staticmethod
    def _content_text(result: object) -> str:
        content = getattr(result, "content", [])
        if not isinstance(content, list):
            return str(content)
        return " ".join(
            str(getattr(item, "text", item.get("text", "") if isinstance(item, Mapping) else ""))
            for item in content
        )

    @classmethod
    def _map_external_error(cls, exc: Exception) -> PubMedProviderError:
        return cls._error_from_text(str(exc))

    @staticmethod
    def _error_from_text(text: str) -> PubMedProviderError:
        normalized = text.casefold()
        if "rate limit" in normalized or "too many requests" in normalized or "429" in normalized:
            return PubMedRateLimitError("PubMed MCP rate limit exceeded")
        if "timeout" in normalized or "timed out" in normalized:
            return PubMedTimeoutError("PubMed MCP request timed out")
        return PubMedUnavailableError("PubMed MCP is unavailable")

    @classmethod
    def _normalize_fetched_article(cls, item: Mapping[str, Any]) -> dict[str, Any]:
        journal_info = item.get("journalInfo")
        journal = journal_info if isinstance(journal_info, Mapping) else {}
        publication_date = journal.get("publicationDate")
        date = publication_date if isinstance(publication_date, Mapping) else {}
        return {
            "pmid": item.get("pmid"),
            "title": item.get("title"),
            "abstract": item.get("abstractText") or "",
            "authors": cls._format_author_records(item.get("authors")),
            "journal": journal.get("title") or journal.get("isoAbbreviation") or "",
            "publication_year": cls._extract_year(date.get("year") or date.get("medlineDate")),
            "doi": item.get("doi"),
            "publication_types": item.get("publicationTypes") or [],
            "url": item.get("pubmedUrl"),
        }

    @staticmethod
    def _format_author_records(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        authors: list[str] = []
        for item in value:
            if not isinstance(item, Mapping):
                continue
            collective = item.get("collectiveName")
            if isinstance(collective, str) and collective.strip():
                authors.append(collective.strip())
                continue
            parts = [item.get("firstName"), item.get("lastName")]
            name = " ".join(
                part.strip() for part in parts if isinstance(part, str) and part.strip()
            )
            if name:
                authors.append(name)
        return authors

    @staticmethod
    def _split_authors(value: object) -> list[str]:
        if not isinstance(value, str):
            return []
        return [item.strip() for item in re.split(r"[,;]", value) if item.strip()]

    @staticmethod
    def _extract_year(value: object) -> int | None:
        if not isinstance(value, str):
            return None
        match = re.search(r"\b(18|19|20|21)\d{2}\b", value)
        return int(match.group(0)) if match else None

    @staticmethod
    def _string_list(value: object, *, field: str) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise PubMedMalformedResponseError(f"MCP {field} must be a string list")
        return value

    @staticmethod
    def _article_from_mapping(value: Mapping[str, Any]) -> PubMedArticle:
        try:
            return PubMedArticle.model_validate(value)
        except ValidationError as exc:
            raise PubMedMalformedResponseError("MCP returned an invalid PubMed article") from exc
