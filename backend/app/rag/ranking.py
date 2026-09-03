from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import replace
from datetime import datetime

from app.rag.hybrid import lexical_tokens
from app.rag.models import RetrievedChunk

_EVIDENCE_PRIOR = {
    "systematic_review_meta_analysis": 1.0,
    "randomized_controlled_trial": 0.9,
    "guideline": 0.9,
    "expert_consensus": 0.8,
    "official_policy_or_reference": 0.8,
    "cohort": 0.7,
    "case_control": 0.6,
    "cross_sectional": 0.5,
    "narrative_review": 0.55,
    "review_unspecified": 0.5,
    "science_communication": 0.35,
    "unknown": 0.25,
}
_POLICY_QUERY = re.compile(
    r"政策|程序|几岁|月龄|剂次|第[一二三四五六七八九十\d]+针|补种|禁忌|规范|指南|现行|最新"
)
_HISTORICAL_QUERY = re.compile(r"历史|早期|曾经|旧版|历年|演变|回顾")


def apply_quality_prior(
    query: str,
    candidates: list[RetrievedChunk],
    *,
    max_adjustment: float = 0.05,
    authority_share: float = 0.65,
    freshness_max_adjustment: float = 0.015,
) -> list[RetrievedChunk]:
    if not 0 <= max_adjustment <= 0.1:
        raise ValueError("quality prior max_adjustment must be between 0 and 0.1")
    if not 0 <= authority_share <= 1:
        raise ValueError("authority_share must be between 0 and 1")
    policy_sensitive = bool(_POLICY_QUERY.search(query))
    historical = bool(_HISTORICAL_QUERY.search(query))
    current_year = datetime.now().year
    adjusted: list[RetrievedChunk] = []
    for candidate in candidates:
        if candidate.is_superseded and not historical:
            continue
        relevance = _candidate_relevance(candidate)
        authority = min(max(candidate.authority_level / 4.0, 0.0), 1.0)
        evidence = _EVIDENCE_PRIOR.get(candidate.evidence_level, 0.25)
        quality = authority_share * authority + (1.0 - authority_share) * evidence
        quality_adjustment = max_adjustment * (2.0 * quality - 1.0)
        if policy_sensitive and candidate.publication_year:
            age = max(0, current_year - candidate.publication_year)
            freshness = max(-1.0, 1.0 - age / 5.0)
            quality_adjustment += freshness_max_adjustment * freshness
        quality_adjustment = min(max(quality_adjustment, -0.1), 0.1)
        adjusted.append(
            replace(
                candidate,
                relevance_score=relevance,
                quality_adjustment=quality_adjustment,
                final_score=min(max(relevance + quality_adjustment, 0.0), 1.0),
            )
        )
    adjusted.sort(
        key=lambda item: (
            -(item.final_score or 0.0),
            -(item.relevance_score or 0.0),
            item.fused_rank or 10**9,
            item.id,
        )
    )
    return [replace(item, final_rank=rank) for rank, item in enumerate(adjusted, start=1)]


def select_diverse(
    candidates: list[RetrievedChunk],
    *,
    top_k: int,
    max_chunks_per_document: int = 2,
    near_duplicate_threshold: float = 0.94,
) -> list[RetrievedChunk]:
    if top_k <= 0:
        return []
    if max_chunks_per_document <= 0:
        raise ValueError("max_chunks_per_document must be positive")
    selected: list[RetrievedChunk] = []
    deferred: list[RetrievedChunk] = []
    document_counts: Counter[str] = Counter()
    seen_content_hashes: set[str] = set()
    for candidate in candidates:
        if _is_duplicate(candidate, selected, seen_content_hashes, near_duplicate_threshold):
            continue
        document_id = candidate.parent_doc_id or candidate.relative_path
        if document_counts[document_id] >= max_chunks_per_document:
            deferred.append(candidate)
            continue
        _select(candidate, selected, document_counts, seen_content_hashes)
        if len(selected) >= top_k:
            return selected
    # Soft constraint: allow overflow only when diversity would otherwise under-fill Top-K.
    for candidate in deferred:
        if _is_duplicate(candidate, selected, seen_content_hashes, near_duplicate_threshold):
            continue
        _select(candidate, selected, document_counts, seen_content_hashes)
        if len(selected) >= top_k:
            break
    return selected


def normalize_reranker_scores(
    candidates: list[RetrievedChunk],
    raw_scores: list[float],
) -> list[RetrievedChunk]:
    if len(candidates) != len(raw_scores):
        raise ValueError("reranker score count mismatch")
    scored = []
    for candidate, raw_score in zip(candidates, raw_scores, strict=True):
        score = raw_score if 0.0 <= raw_score <= 1.0 else 1.0 / (1.0 + math.exp(-raw_score))
        scored.append(replace(candidate, reranker_score=score, relevance_score=score))
    scored.sort(
        key=lambda item: (
            -(item.relevance_score or 0.0),
            item.fused_rank or 10**9,
            item.id,
        )
    )
    return scored


def _candidate_relevance(candidate: RetrievedChunk) -> float:
    if candidate.relevance_score is not None:
        return candidate.relevance_score
    if candidate.reranker_score is not None:
        return candidate.reranker_score
    return min(max(candidate.similarity, 0.0), 1.0)


def _is_duplicate(
    candidate: RetrievedChunk,
    selected: list[RetrievedChunk],
    seen_hashes: set[str],
    threshold: float,
) -> bool:
    if candidate.content_hash and candidate.content_hash in seen_hashes:
        return True
    candidate_tokens = set(lexical_tokens(candidate.text))
    if not candidate_tokens:
        return False
    for existing in selected:
        existing_tokens = set(lexical_tokens(existing.text))
        union = candidate_tokens | existing_tokens
        if union and len(candidate_tokens & existing_tokens) / len(union) >= threshold:
            return True
    return False


def _select(
    candidate: RetrievedChunk,
    selected: list[RetrievedChunk],
    counts: Counter[str],
    seen_hashes: set[str],
) -> None:
    selected.append(candidate)
    counts[candidate.parent_doc_id or candidate.relative_path] += 1
    if candidate.content_hash:
        seen_hashes.add(candidate.content_hash)
