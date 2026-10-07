from __future__ import annotations

import re
from dataclasses import dataclass, replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.pubmed.models import PubMedArticle
from app.pubmed.query import extract_named_identifiers
from app.rag.models import RagSource

_SPACE_PATTERN = re.compile(r"\s+")
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "ref", "source"}
_SOURCE_MARKER_PATTERN = re.compile(r"\[\[(local:\d+|pubmed:\d{1,10})\]\]")


@dataclass(frozen=True, slots=True)
class CitationBinding:
    answer: str
    rag_sources: list[RagSource]
    pubmed_articles: list[PubMedArticle]


def bind_cited_sources(
    answer: str,
    source_ids: list[str] | None,
    rag_sources: list[RagSource],
    pubmed_articles: list[PubMedArticle],
) -> CitationBinding:
    """Keep only evidence explicitly bound to a sentence and renumber markers."""

    if source_ids is None:
        return CitationBinding(
            answer=answer,
            rag_sources=deduplicate_rag_sources(rag_sources),
            pubmed_articles=deduplicate_pubmed_articles(pubmed_articles),
        )

    requested = list(dict.fromkeys(source_ids))
    marked = set(_SOURCE_MARKER_PATTERN.findall(answer))
    accepted = [source_id for source_id in requested if source_id in marked]
    local_by_id = {f"local:{index}": source for index, source in enumerate(rag_sources, 1)}
    pubmed_by_id = {f"pubmed:{item.pmid}": item for item in pubmed_articles}
    selected_local = deduplicate_rag_sources(
        [local_by_id[item] for item in accepted if item in local_by_id]
    )
    selected_pubmed = deduplicate_pubmed_articles(
        [pubmed_by_id[item] for item in accepted if item in pubmed_by_id]
    )

    number_by_id: dict[str, int] = {}
    local_number_by_key = {
        _rag_document_key(source): index for index, source in enumerate(selected_local, 1)
    }
    for source_id, source in local_by_id.items():
        key = _rag_document_key(source)
        if source_id in accepted and key in local_number_by_key:
            number_by_id[source_id] = local_number_by_key[key]
    offset = len(selected_local)
    for index, article in enumerate(selected_pubmed, 1):
        number_by_id[f"pubmed:{article.pmid}"] = offset + index

    def replace_marker(match: re.Match[str]) -> str:
        number = number_by_id.get(match.group(1))
        return f"［{number}］" if number is not None else ""

    return CitationBinding(
        answer=_SOURCE_MARKER_PATTERN.sub(replace_marker, answer),
        rag_sources=selected_local,
        pubmed_articles=selected_pubmed,
    )


def deduplicate_rag_sources(sources: list[RagSource]) -> list[RagSource]:
    """Collapse retrieval chunks into document-level sources.

    Retrieval still keeps multiple chunks for answer generation.  This function is
    deliberately applied only to the user-facing source list, where several pages
    from one document must not look like independent publications.
    """

    grouped: dict[str, RagSource] = {}
    order: list[str] = []
    for source in sources:
        key = _rag_document_key(source)
        existing = grouped.get(key)
        if existing is None:
            pages = tuple(sorted({source.page} if source.page is not None else set()))
            grouped[key] = replace(source, pages=pages)
            order.append(key)
            continue

        excerpts = _merge_distinct_text(existing.content, source.content, limit=1200)
        sections = _merge_distinct_text(existing.section, source.section, limit=300)
        pages = tuple(
            sorted(
                {
                    *existing.pages,
                    *({existing.page} if existing.page is not None else set()),
                    *({source.page} if source.page is not None else set()),
                }
            )
        )
        grouped[key] = replace(existing, content=excerpts, section=sections, pages=pages)
    return [grouped[key] for key in order]


def deduplicate_pubmed_articles(articles: list[PubMedArticle]) -> list[PubMedArticle]:
    seen: set[str] = set()
    unique: list[PubMedArticle] = []
    for article in articles:
        key = f"pmid:{article.pmid}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


def filter_pubmed_articles(
    question: str,
    articles: list[PubMedArticle],
) -> list[PubMedArticle]:
    """Apply conservative topic gates to high-risk ambiguous vaccine searches.

    PubMed ranking alone is not evidence entailment.  These gates cover concepts
    whose Chinese-to-English ambiguity produced observed false positives, and
    named biomedical identifiers that must survive into the returned paper.
    """

    unique = deduplicate_pubmed_articles(articles)
    return [article for article in unique if _article_matches_question(question, article)]


def _article_matches_question(question: str, article: PubMedArticle) -> bool:
    query = question.casefold()
    evidence = f"{article.title}\n{article.abstract}".casefold()

    # “发烧/发热” must not be expanded to the disease “yellow fever”.
    if re.search(r"发烧|发热", query) and "黄热" not in query:
        if "yellow fever" in evidence and not re.search(
            r"acute (?:febrile|fever)|febrile (?:illness|child)|vaccin(?:e|ation).{0,40}fever",
            evidence,
        ):
            return False

    concept_gates: list[tuple[bool, tuple[tuple[str, ...], ...]]] = [
        (
            bool(re.search(r"哺乳|喂奶|母乳", query) and re.search(r"流感", query)),
            (
                ("breastfeed", "breast-feeding", "lactat", "nursing mother"),
                ("influenza", "flu vaccin"),
            ),
        ),
        (
            bool(re.search(r"鸡蛋|蛋清|卵蛋白", query) and re.search(r"流感", query)),
            (("egg allerg", "egg-allerg", "ovalbumin"), ("influenza", "flu vaccin")),
        ),
        (
            bool(
                re.search(r"免疫球蛋白|丙种球蛋白", query) and re.search(r"麻腮风|麻疹|mmr", query)
            ),
            (
                ("immunoglobulin", "immune globulin", "antibody-containing"),
                ("measles", "mumps", "rubella", "mmr", "live attenuated vaccin"),
            ),
        ),
        (
            bool(re.search(r"百白破|dtap", query)),
            (("dtap", "pertussis", "diphtheria", "tetanus"),),
        ),
    ]
    for active, required_groups in concept_gates:
        if active and any(not any(term in evidence for term in group) for group in required_groups):
            return False

    identifiers = extract_named_identifiers(question)
    if identifiers and not any(identifier.casefold() in evidence for identifier in identifiers):
        return False
    return True


def _rag_document_key(source: RagSource) -> str:
    if source.document_id:
        return f"doc:{source.document_id.casefold()}"
    if source.source_url:
        return f"url:{_normalize_url(source.source_url)}"
    return f"file:{_SPACE_PATTERN.sub('', source.file_name).casefold()}"


def _normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_QUERY_KEYS
        )
    )
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path.rstrip("/"),
            query,
            "",
        )
    )


def _merge_distinct_text(
    first: str | None,
    second: str | None,
    *,
    limit: int,
) -> str | None:
    parts: list[str] = []
    seen: set[str] = set()
    for value in (first, second):
        if not value:
            continue
        for paragraph in re.split(r"\n\s*\n", value):
            normalized = _SPACE_PATTERN.sub(" ", paragraph).strip()
            fingerprint = normalized.casefold()
            if not normalized or fingerprint in seen:
                continue
            seen.add(fingerprint)
            parts.append(normalized)
    if not parts:
        return None
    return "\n\n".join(parts)[:limit].rstrip()
