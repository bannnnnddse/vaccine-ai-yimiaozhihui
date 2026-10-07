import asyncio
import time
from collections.abc import Mapping
from xml.etree.ElementTree import Element

import httpx
from defusedxml import ElementTree
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

_EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class DirectPubMedProvider(PubMedProvider):
    """Official NCBI E-utilities adapter using ESearch followed by EFetch."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str | None = None,
        email: str | None = None,
        tool: str = "vaccine-ai-backend",
        timeout_seconds: float = 20,
        retries: int = 1,
        max_results: int = 5,
        max_query_length: int = 500,
        request_interval_seconds: float | None = None,
    ) -> None:
        super().__init__(max_results=max_results, max_query_length=max_query_length)
        if timeout_seconds <= 0:
            raise ValueError("NCBI timeout must be positive")
        if not 0 <= retries <= 3:
            raise ValueError("NCBI retries must be between 0 and 3")
        normalized_tool = tool.strip()
        if not normalized_tool or any(character.isspace() for character in normalized_tool):
            raise ValueError("NCBI tool must be non-empty and contain no spaces")
        self._client = client
        self._api_key = api_key.strip() if api_key else None
        self._email = email.strip() if email else None
        self._tool = normalized_tool
        self._timeout_seconds = timeout_seconds
        self._retries = retries
        self._request_interval_seconds = (
            request_interval_seconds
            if request_interval_seconds is not None
            else (0.11 if self._api_key else 0.34)
        )
        if self._request_interval_seconds < 0:
            raise ValueError("NCBI request interval cannot be negative")
        self._request_lock = asyncio.Lock()
        self._last_request_started = 0.0

    async def _search_articles(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[PubMedArticle]:
        response = await self._request(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance",
            },
        )
        try:
            payload = response.json()
            pmids = payload["esearchresult"]["idlist"]
        except (ValueError, KeyError, TypeError) as exc:
            raise PubMedMalformedResponseError("NCBI ESearch returned invalid JSON") from exc
        if not isinstance(pmids, list) or any(not isinstance(pmid, str) for pmid in pmids):
            raise PubMedMalformedResponseError("NCBI ESearch idlist must be a string list")
        if not pmids:
            return []
        return await self._fetch_articles(pmids[:max_results])

    async def _fetch_articles(self, pmids: list[str]) -> list[PubMedArticle]:
        response = await self._request(
            "efetch.fcgi",
            {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
        )
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as exc:
            raise PubMedMalformedResponseError("NCBI EFetch returned invalid XML") from exc
        if root.tag != "PubmedArticleSet":
            raise PubMedMalformedResponseError("NCBI EFetch response has an invalid root element")

        articles: list[PubMedArticle] = []
        for item in root.findall("./PubmedArticle")[: self.max_results]:
            article = self._parse_article(item)
            if article is not None:
                articles.append(article)
        return articles

    async def _request(self, endpoint: str, params: Mapping[str, object]) -> httpx.Response:
        request_params = {
            **params,
            "tool": self._tool,
            **({"email": self._email} if self._email else {}),
            **({"api_key": self._api_key} if self._api_key else {}),
        }
        last_error: PubMedProviderError | None = None
        for attempt in range(self._retries + 1):
            try:
                await self._respect_rate_limit()
                response = await asyncio.wait_for(
                    self._client.get(f"{_EUTILS_BASE_URL}/{endpoint}", params=request_params),
                    timeout=self._timeout_seconds,
                )
                if response.status_code == 429:
                    raise PubMedRateLimitError("NCBI E-utilities rate limit exceeded")
                if response.status_code >= 500:
                    raise PubMedUnavailableError("NCBI E-utilities is temporarily unavailable")
                response.raise_for_status()
                return response
            except (TimeoutError, httpx.TimeoutException) as exc:
                last_error = PubMedTimeoutError("NCBI E-utilities request timed out")
                last_error.__cause__ = exc
            except PubMedRateLimitError as exc:
                last_error = exc
            except PubMedUnavailableError as exc:
                last_error = exc
            except httpx.HTTPError as exc:
                last_error = PubMedUnavailableError("NCBI E-utilities request failed")
                last_error.__cause__ = exc
            if attempt < self._retries:
                await asyncio.sleep(0)
        if last_error is None:  # pragma: no cover
            raise PubMedUnavailableError("NCBI E-utilities request failed")
        raise last_error

    async def _respect_rate_limit(self) -> None:
        async with self._request_lock:
            elapsed = time.monotonic() - self._last_request_started
            delay = self._request_interval_seconds - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request_started = time.monotonic()

    @classmethod
    def _parse_article(cls, item: Element) -> PubMedArticle | None:
        pmid = cls._text(item.find("./MedlineCitation/PMID"))
        if not pmid:
            return None
        article_node = item.find("./MedlineCitation/Article")
        if article_node is None:
            return None
        title = cls._iter_text(article_node.find("./ArticleTitle")) or f"PubMed article PMID {pmid}"
        abstract_parts: list[str] = []
        for abstract_node in article_node.findall("./Abstract/AbstractText"):
            text = cls._iter_text(abstract_node)
            if not text:
                continue
            label = abstract_node.attrib.get("Label", "").strip()
            abstract_parts.append(f"{label}: {text}" if label else text)

        authors: list[str] = []
        for author in article_node.findall("./AuthorList/Author"):
            collective = cls._text(author.find("./CollectiveName"))
            if collective:
                authors.append(collective)
                continue
            name = " ".join(
                part
                for part in [
                    cls._text(author.find("./ForeName")),
                    cls._text(author.find("./LastName")),
                ]
                if part
            )
            if name:
                authors.append(name)

        journal = cls._iter_text(article_node.find("./Journal/Title"))
        year_text = cls._text(article_node.find("./Journal/JournalIssue/PubDate/Year"))
        if not year_text:
            year_text = cls._text(
                article_node.find("./Journal/JournalIssue/PubDate/MedlineDate")
            )
        doi = None
        for identifier in item.findall("./PubmedData/ArticleIdList/ArticleId"):
            if identifier.attrib.get("IdType") == "doi":
                doi = cls._text(identifier)
                break
        publication_types = [
            text
            for node in article_node.findall("./PublicationTypeList/PublicationType")
            if (text := cls._iter_text(node))
        ]
        try:
            return PubMedArticle(
                pmid=pmid,
                title=title,
                abstract="\n".join(abstract_parts),
                authors=authors,
                journal=journal,
                publication_year=cls._extract_year(year_text),
                doi=doi,
                publication_types=publication_types,
            )
        except ValidationError as exc:
            raise PubMedMalformedResponseError("NCBI returned an invalid article") from exc

    @staticmethod
    def _text(node: Element | None) -> str:
        return node.text.strip() if node is not None and node.text else ""

    @staticmethod
    def _iter_text(node: Element | None) -> str:
        return "" if node is None else "".join(node.itertext()).strip()

    @staticmethod
    def _extract_year(value: str) -> int | None:
        for token in value.replace("-", " ").split():
            if len(token) == 4 and token.isdigit():
                return int(token)
        return None
