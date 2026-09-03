import pytest

from app.pubmed.models import PubMedArticle
from app.pubmed.provider import PubMedProvider


class FakeProvider(PubMedProvider):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.search_call: tuple[str, int] | None = None
        self.fetch_call: list[str] | None = None

    async def _search_articles(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[PubMedArticle]:
        self.search_call = (query, max_results)
        return [PubMedArticle(pmid="123", title="Vaccine evidence")]

    async def _fetch_articles(self, pmids: list[str]) -> list[PubMedArticle]:
        self.fetch_call = pmids
        return [PubMedArticle(pmid=pmid, title=f"Article {pmid}") for pmid in pmids]


def test_article_normalizes_fields_and_adds_canonical_url() -> None:
    article = PubMedArticle(
        pmid="12345",
        title="  Vaccine study  ",
        authors=[" Alice ", "", "Bob"],
        publication_types=[" Randomized Controlled Trial "],
    )

    assert article.title == "Vaccine study"
    assert article.authors == ["Alice", "Bob"]
    assert article.url == "https://pubmed.ncbi.nlm.nih.gov/12345/"


@pytest.mark.asyncio
async def test_provider_validates_and_normalizes_search() -> None:
    provider = FakeProvider(max_results=5, max_query_length=100)

    articles = await provider.search_articles("  HPV vaccine safety  ", max_results=3)

    assert [article.pmid for article in articles] == ["123"]
    assert provider.search_call == ("HPV vaccine safety", 3)


@pytest.mark.asyncio
async def test_provider_rejects_oversized_or_blank_query() -> None:
    provider = FakeProvider(max_query_length=50)

    with pytest.raises(ValueError, match="blank"):
        await provider.search_articles("  ")
    with pytest.raises(ValueError, match="length limit"):
        await provider.search_articles("x" * 51)


@pytest.mark.asyncio
async def test_provider_validates_deduplicates_and_limits_pmids() -> None:
    provider = FakeProvider(max_results=2)

    articles = await provider.fetch_articles([" 123 ", "123", "456"])

    assert [article.pmid for article in articles] == ["123", "456"]
    assert provider.fetch_call == ["123", "456"]
    with pytest.raises(ValueError, match="numeric"):
        await provider.fetch_articles(["PMID123"])
    with pytest.raises(ValueError, match="count"):
        await provider.fetch_articles(["1", "2", "3"])


@pytest.mark.asyncio
async def test_provider_rejects_result_limit_above_policy() -> None:
    provider = FakeProvider(max_results=5)

    with pytest.raises(ValueError, match="configured maximum"):
        await provider.search_articles("vaccines", max_results=6)
