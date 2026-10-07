"""Deterministic source filtering, document deduplication and citation validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import PurePath
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.pubmed.models import PubMedArticle
from app.pubmed.query import extract_named_identifiers, is_current_illness_vaccination_question
from app.rag.models import RagSource

_TRACKING_PARAMS = {"ref", "source", "fbclid", "gclid"}
_MARKER_RE = re.compile(r"\[\[(local:[A-Za-z0-9._-]+|pubmed:\d{1,10})\]\]")
_SPACE_RE = re.compile(r"\s+")
FAIL_CLOSED_ANSWER = "当前证据不足以确认具体医学结论，建议咨询接种机构、医生或官方卫生部门。"


@dataclass(frozen=True, slots=True)
class CitationAuditResult:
    answer: str
    source_ids: tuple[str, ...]
    session_id: str = ""
    is_vaccine_related: bool = True


@dataclass(frozen=True, slots=True)
class FinalizedCitations:
    answer: str
    sources: tuple[RagSource | PubMedArticle, ...]


def cited_source_ids(answer: str) -> tuple[str, ...]:
    """Read exact machine markers without interpreting prose as evidence."""
    return tuple(dict.fromkeys(match.group(1) for match in _MARKER_RE.finditer(answer)))


def normalize_source_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return value.strip() or None
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        return value.strip() or None
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_PARAMS
        ]
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, query, ""))


def _filename_key(value: str) -> str:
    return _SPACE_RE.sub("", PurePath(value.replace("\\", "/")).name).casefold()


def document_key(source: RagSource) -> str:
    if source.document_id and source.document_id.strip():
        return f"doc:{source.document_id.strip().casefold()}"
    normalized_url = normalize_source_url(source.source_url)
    if normalized_url:
        return f"url:{normalized_url}"
    return f"file:{_filename_key(source.file_name)}"


def deduplicate_local_sources(
    sources: list[RagSource], *, max_content_chars: int = 1200
) -> list[RagSource]:
    grouped: dict[str, list[RagSource]] = {}
    order: list[str] = []
    for source in sources:
        key = document_key(source)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(source)

    merged: list[RagSource] = []
    for index, key in enumerate(order, start=1):
        items = grouped[key]
        first = items[0]
        snippets: list[str] = []
        seen_snippets: set[str] = set()
        for item in items:
            snippet = item.content.strip()
            if snippet and snippet not in seen_snippets:
                seen_snippets.add(snippet)
                snippets.append(snippet)
        content = "\n\n".join(snippets)[:max_content_chars].rstrip()
        pages = tuple(
            sorted(
                {
                    page
                    for item in items
                    for page in (
                        *item.pages,
                        *((item.page,) if item.page is not None else ()),
                    )
                    if page > 0
                }
            )
        )
        merged.append(
            replace(
                first,
                page=pages[0] if pages else first.page,
                pages=pages if len(pages) >= 2 else (),
                content=content,
                source_url=normalize_source_url(first.source_url),
                source_id=f"local:{index}",
            )
        )
    return merged


def assign_local_source_ids(sources: list[RagSource]) -> list[RagSource]:
    """Give retrieval-order IDs to chunk evidence without changing document identity."""

    return [replace(source, source_id=f"local:{index}") for index, source in enumerate(sources, 1)]


def deduplicate_pubmed_articles(articles: list[PubMedArticle]) -> list[PubMedArticle]:
    result: list[PubMedArticle] = []
    seen: set[str] = set()
    for article in articles:
        if article.pmid in seen:
            continue
        seen.add(article.pmid)
        result.append(article)
    return result


def select_related_pubmed_excerpt(
    question: str, articles: list[PubMedArticle]
) -> tuple[PubMedArticle, str] | None:
    """Pick the most relevant abstract sentence for answer synthesis and display."""

    if not articles:
        return None
    illness_question = is_current_illness_vaccination_question(question)
    best: tuple[int, int, PubMedArticle, str] | None = None
    for article_index, article in enumerate(articles):
        sentences = re.split(r"(?<=[.!?])\s+", article.abstract.strip())
        if not sentences or not sentences[0]:
            sentences = [article.title]
        for sentence in sentences:
            excerpt = sentence.strip()[:600]
            if not excerpt:
                continue
            text = excerpt.casefold()
            score = 0
            if any(term in text for term in ("vaccin", "immuniz")):
                score += 2
            if illness_question:
                if any(term in text for term in (
                    "illness", "influenza", "infection", "febrile", "fever",
                )):
                    score += 3
                if any(term in text for term in ("child", "infant", "pediatric")):
                    score += 1
            else:
                latin_terms = set(re.findall(r"[a-z][a-z0-9-]{2,}", question.casefold()))
                score += sum(term in text for term in latin_terms)
            candidate = (score, -article_index, article, excerpt)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    if best is None:
        return None
    return best[2], best[3]


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

def finalize_audited_citations(
    audit: CitationAuditResult,
    local_sources: list[RagSource],
    pubmed_articles: list[PubMedArticle],
) -> FinalizedCitations:
    local_by_id = {item.source_id: item for item in local_sources if item.source_id}
    pubmed_by_id = {f"pubmed:{item.pmid}": item for item in pubmed_articles}
    available: dict[str, RagSource | PubMedArticle] = {**local_by_id, **pubmed_by_id}
    declared = set(audit.source_ids)
    marker_ids = [match.group(1) for match in _MARKER_RE.finditer(audit.answer)]
    valid_ids = {item for item in declared if item in available and item in marker_ids}
    number_by_document: dict[str, int] = {}
    source_by_number: dict[int, RagSource | PubMedArticle] = {}

    def replace_marker(match: re.Match[str]) -> str:
        source_id = match.group(1)
        if source_id not in valid_ids:
            return ""
        source = available[source_id]
        key = document_key(source) if isinstance(source, RagSource) else f"pmid:{source.pmid}"
        if key not in number_by_document:
            number = len(number_by_document) + 1
            number_by_document[key] = number
            source_by_number[number] = source
        return f"［{number_by_document[key]}］"

    answer = _MARKER_RE.sub(replace_marker, audit.answer).strip()
    ordered: list[RagSource | PubMedArticle] = []
    for source in source_by_number.values():
        if isinstance(source, PubMedArticle):
            ordered.append(source)
            continue
        siblings = [item for item in local_sources if document_key(item) == document_key(source)]
        ordered.append(deduplicate_local_sources(siblings)[0])
    return FinalizedCitations(answer=answer, sources=tuple(ordered))


# Compatibility for the existing orchestration and its public helper contract.
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
    return deduplicate_local_sources(sources)


_SOURCE_MARKER_PATTERN = _MARKER_RE
_rag_document_key = document_key
