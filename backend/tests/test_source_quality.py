import pytest

from app.pubmed.models import PubMedArticle
from app.rag.models import RagSource
from app.services.source_quality import (
    bind_cited_sources,
    deduplicate_rag_sources,
    filter_pubmed_articles,
)


def test_document_chunks_are_merged_into_one_user_facing_source() -> None:
    sources = [
        RagSource(file_name="百白破技术方案.pdf", page=3, content="补种未完成剂次。"),
        RagSource(file_name="百白破技术方案.pdf", page=7, content="剂次之间有最小间隔。"),
        RagSource(file_name="百白破技术方案.pdf", page=3, content="补种未完成剂次。"),
    ]

    result = deduplicate_rag_sources(sources)

    assert len(result) == 1
    assert result[0].pages == (3, 7)
    assert result[0].content == "补种未完成剂次。\n\n剂次之间有最小间隔。"


def test_web_sources_are_deduplicated_by_normalized_url() -> None:
    sources = [
        RagSource(
            file_name="页面 A",
            page=None,
            content="证据一",
            source_type="web",
            source_url="https://example.org/guide/?utm_source=test#part",
        ),
        RagSource(
            file_name="页面 B",
            page=None,
            content="证据二",
            source_type="web",
            source_url="https://EXAMPLE.org/guide",
        ),
    ]

    result = deduplicate_rag_sources(sources)

    assert len(result) == 1
    assert result[0].content == "证据一\n\n证据二"


def test_fever_question_rejects_yellow_fever_false_positive() -> None:
    articles = [
        PubMedArticle(
            pmid="1",
            title="Yellow fever vaccination in children",
            abstract="Immunity after yellow fever vaccination.",
        ),
        PubMedArticle(
            pmid="2",
            title="Vaccination during acute febrile illness",
            abstract="Clinical guidance for a febrile child.",
        ),
    ]

    result = filter_pubmed_articles("孩子发烧 38.2℃ 能接种疫苗吗", articles)

    assert [article.pmid for article in result] == ["2"]


def test_lactation_influenza_requires_both_concepts() -> None:
    articles = [
        PubMedArticle(pmid="1", title="COVID-19 vaccination in lactation"),
        PubMedArticle(pmid="2", title="Influenza vaccine hesitancy survey"),
        PubMedArticle(
            pmid="3",
            title="Influenza vaccination in breastfeeding mothers",
        ),
    ]

    result = filter_pubmed_articles("哺乳期能接种流感疫苗吗", articles)

    assert [article.pmid for article in result] == ["3"]


def test_immunoglobulin_mmr_requires_interaction_evidence() -> None:
    articles = [
        PubMedArticle(pmid="1", title="MMR revaccination in children"),
        PubMedArticle(pmid="2", title="Pneumococcal vaccine immunogenicity"),
        PubMedArticle(
            pmid="3",
            title="Immune globulin interference with measles vaccination",
        ),
    ]

    result = filter_pubmed_articles("免疫球蛋白后多久能打麻腮风疫苗", articles)

    assert [article.pmid for article in result] == ["3"]


def test_only_sentence_bound_sources_are_exposed_and_duplicate_markers_collapse() -> None:
    local = [
        RagSource(file_name="接种规范.pdf", page=3, content="应暂缓接种。"),
        RagSource(file_name="接种规范.pdf", page=8, content="康复后补种。"),
        RagSource(file_name="冷链规范.pdf", page=2, content="冷链温度。"),
    ]
    pubmed = [
        PubMedArticle(pmid="10", title="Relevant evidence"),
        PubMedArticle(pmid="11", title="Unused evidence"),
    ]

    result = bind_cited_sources(
        "发热期间应暂缓。[[local:1]]康复后补种。[[local:2]]研究也支持。[[pubmed:10]]",
        ["local:1", "local:2", "pubmed:10", "pubmed:11"],
        local,
        pubmed,
    )

    assert result.answer == "发热期间应暂缓。［1］康复后补种。［1］研究也支持。［2］"
    assert len(result.rag_sources) == 1
    assert [article.pmid for article in result.pubmed_articles] == ["10"]


def test_explicit_empty_citation_audit_fails_closed() -> None:
    result = bind_cited_sources(
        "没有直接证据的受限回答。",
        [],
        [RagSource(file_name="无关.pdf", page=1, content="无关片段")],
        [PubMedArticle(pmid="10", title="Unrelated")],
    )

    assert result.rag_sources == []
    assert result.pubmed_articles == []


@pytest.mark.parametrize(
    ("case_id", "question", "articles", "expected_pmids"),
    [
        (
            "SCI-001",
            "孩子发烧 38.2℃ 能接种疫苗吗",
            [
                PubMedArticle(pmid="101", title="Yellow fever vaccination in children"),
                PubMedArticle(pmid="102", title="Vaccination during acute febrile illness"),
            ],
            ["102"],
        ),
        (
            "SCI-002",
            "鸡蛋过敏能接种流感疫苗吗",
            [
                PubMedArticle(pmid="201", title="Yellow fever vaccine in egg allergy"),
                PubMedArticle(pmid="202", title="Influenza vaccination in egg-allergic children"),
            ],
            ["202"],
        ),
        (
            "SCI-004",
            "哺乳期能接种流感疫苗吗",
            [
                PubMedArticle(pmid="401", title="COVID-19 vaccination during lactation"),
                PubMedArticle(pmid="402", title="Influenza vaccination while breastfeeding"),
            ],
            ["402"],
        ),
        (
            "SCI-017",
            "免疫球蛋白后多久能打麻腮风疫苗",
            [
                PubMedArticle(pmid="1701", title="MMR booster effectiveness"),
                PubMedArticle(pmid="1702", title="Immune globulin interference with MMR vaccine"),
            ],
            ["1702"],
        ),
    ],
)
def test_scientific_cases_reject_weak_or_ambiguous_pubmed_results(
    case_id: str,
    question: str,
    articles: list[PubMedArticle],
    expected_pmids: list[str],
) -> None:
    assert case_id.startswith("SCI-")
    assert [item.pmid for item in filter_pubmed_articles(question, articles)] == expected_pmids


@pytest.mark.parametrize(
    ("case_id", "file_name", "repetitions"),
    [
        ("SCI-002", "早产儿、过敏体质儿童等，能接种疫苗吗？.md", 3),
        ("SCI-006", "百白破程序调整实施技术方案.pdf", 4),
        ("SCI-015", "百白破程序调整实施技术方案.pdf", 3),
    ],
)
def test_scientific_cases_collapse_repeated_document_chunks(
    case_id: str,
    file_name: str,
    repetitions: int,
) -> None:
    sources = [
        RagSource(file_name=file_name, page=index + 1, content=f"片段 {index + 1}")
        for index in range(repetitions)
    ]

    result = deduplicate_rag_sources(sources)

    assert case_id.startswith("SCI-")
    assert len(result) == 1
    assert result[0].pages == tuple(range(1, repetitions + 1))
