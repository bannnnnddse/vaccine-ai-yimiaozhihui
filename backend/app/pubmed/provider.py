from abc import ABC, abstractmethod

from app.pubmed.models import PubMedArticle


class PubMedProviderError(Exception):
    """Base error safe for orchestration-level fallback handling."""


class PubMedTimeoutError(PubMedProviderError):
    pass


class PubMedRateLimitError(PubMedProviderError):
    pass


class PubMedUnavailableError(PubMedProviderError):
    pass


class PubMedMalformedResponseError(PubMedProviderError):
    pass


class PubMedProvider(ABC):
    """Read-only provider boundary shared by MCP and direct NCBI implementations."""

    def __init__(self, *, max_results: int = 5, max_query_length: int = 500) -> None:
        if not 1 <= max_results <= 20:
            raise ValueError("PubMed max_results must be between 1 and 20")
        if not 50 <= max_query_length <= 2000:
            raise ValueError("PubMed max_query_length must be between 50 and 2000")
        self.max_results = max_results
        self.max_query_length = max_query_length

    async def search_articles(
        self,
        query: str,
        *,
        max_results: int | None = None,
    ) -> list[PubMedArticle]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("PubMed query cannot be blank")
        if len(normalized_query) > self.max_query_length:
            raise ValueError("PubMed query exceeds configured length limit")
        limit = self._validate_result_limit(max_results)
        return await self._search_articles(normalized_query, max_results=limit)

    async def fetch_articles(self, pmids: list[str]) -> list[PubMedArticle]:
        normalized_pmids = self._validate_pmids(pmids)
        return await self._fetch_articles(normalized_pmids)

    async def find_related(
        self,
        pmid: str,
        *,
        max_results: int | None = None,
    ) -> list[PubMedArticle]:
        normalized_pmid = self._validate_pmids([pmid])[0]
        limit = self._validate_result_limit(max_results)
        return await self._find_related(normalized_pmid, max_results=limit)

    def _validate_result_limit(self, requested: int | None) -> int:
        limit = self.max_results if requested is None else requested
        if not 1 <= limit <= self.max_results:
            raise ValueError("requested PubMed result limit exceeds configured maximum")
        return limit

    def _validate_pmids(self, pmids: list[str]) -> list[str]:
        if not pmids:
            raise ValueError("at least one PMID is required")
        normalized: list[str] = []
        for pmid in pmids:
            value = pmid.strip()
            if not value.isdigit() or len(value) > 10:
                raise ValueError("PMIDs must be numeric strings of at most 10 digits")
            if value not in normalized:
                normalized.append(value)
        if len(normalized) > self.max_results:
            raise ValueError("PMID count exceeds configured maximum")
        return normalized

    @abstractmethod
    async def _search_articles(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[PubMedArticle]: ...

    @abstractmethod
    async def _fetch_articles(self, pmids: list[str]) -> list[PubMedArticle]: ...

    async def _find_related(
        self,
        pmid: str,
        *,
        max_results: int,
    ) -> list[PubMedArticle]:
        raise NotImplementedError("related article lookup is not supported by this provider")
