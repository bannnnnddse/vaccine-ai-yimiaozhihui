from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import replace

from app.rag.models import RetrievedChunk, TextChunk

_TOKEN_PATTERN = re.compile(r"[a-zA-Z]+(?:[-_.]?[a-zA-Z0-9]+)*|\d+(?:\.\d+)?|[\u3400-\u9fff]+")


def lexical_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(value.casefold()):
        part = match.group(0)
        if "\u3400" <= part[0] <= "\u9fff":
            characters = list(part)
            tokens.extend(characters)
            tokens.extend(
                characters[index] + characters[index + 1]
                for index in range(len(characters) - 1)
            )
        else:
            tokens.append(part)
    return tokens


class Bm25Index:
    def __init__(self, chunks: list[TextChunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._chunks = chunks
        self._k1 = k1
        self._b = b
        self._lengths: list[int] = []
        self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, chunk in enumerate(chunks):
            # The answer model receives document and section metadata in each
            # knowledge block. Include that same governed metadata in BM25 so
            # exact identifiers present in an imported filename/title are not
            # invisible to lexical retrieval (for example Com-COV2 and 9900万).
            lexical_text = "\n".join(
                value
                for value in (
                    chunk.embedding_text or chunk.text,
                    chunk.file_name,
                    chunk.source_title,
                    chunk.title,
                    chunk.section,
                )
                if value
            )
            frequencies = Counter(lexical_tokens(lexical_text))
            self._lengths.append(sum(frequencies.values()))
            for token, frequency in frequencies.items():
                self._postings[token].append((index, frequency))
        self._average_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )

    def query(self, query_text: str, *, top_k: int) -> list[RetrievedChunk]:
        if not self._chunks or top_k <= 0:
            return []
        query_terms = Counter(lexical_tokens(query_text))
        scores: dict[int, float] = defaultdict(float)
        document_count = len(self._chunks)
        for token, query_frequency in query_terms.items():
            postings = self._postings.get(token, [])
            if not postings:
                continue
            document_frequency = len(postings)
            inverse_document_frequency = math.log(
                1.0 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            for index, term_frequency in postings:
                length = self._lengths[index]
                normalization = 1.0 - self._b
                if self._average_length:
                    normalization += self._b * length / self._average_length
                numerator = term_frequency * (self._k1 + 1.0)
                denominator = term_frequency + self._k1 * normalization
                scores[index] += (
                    query_frequency * inverse_document_frequency * numerator / denominator
                )
        if not scores:
            return []
        ranked = sorted(scores.items(), key=lambda item: (-item[1], self._chunks[item[0]].id))
        return [
            _as_retrieved(
                self._chunks[index],
                lexical_rank=rank,
                lexical_score=score,
            )
            for rank, (index, score) in enumerate(ranked[:top_k], start=1)
        ]


def reciprocal_rank_fusion(
    dense: list[RetrievedChunk],
    lexical: list[RetrievedChunk],
    *,
    rrf_k: int = 60,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")
    candidates: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = defaultdict(float)
    dense_ranks: dict[str, int] = {}
    lexical_ranks: dict[str, int] = {}
    lexical_scores: dict[str, float] = {}
    for rank, chunk in enumerate(dense, start=1):
        candidates.setdefault(chunk.id, chunk)
        dense_ranks.setdefault(chunk.id, rank)
        scores[chunk.id] += 1.0 / (rrf_k + rank)
    for rank, chunk in enumerate(lexical, start=1):
        candidates.setdefault(chunk.id, chunk)
        lexical_ranks.setdefault(chunk.id, rank)
        if chunk.lexical_score is not None:
            lexical_scores[chunk.id] = chunk.lexical_score
        scores[chunk.id] += 1.0 / (rrf_k + rank)
    ranked_ids = sorted(
        candidates,
        key=lambda chunk_id: (
            -scores[chunk_id],
            dense_ranks.get(chunk_id, 10**9),
            lexical_ranks.get(chunk_id, 10**9),
            chunk_id,
        ),
    )
    if limit is not None:
        ranked_ids = ranked_ids[:limit]
    return [
        replace(
            candidates[chunk_id],
            dense_rank=dense_ranks.get(chunk_id),
            lexical_rank=lexical_ranks.get(chunk_id),
            lexical_score=lexical_scores.get(chunk_id),
            rrf_score=scores[chunk_id],
            fused_rank=rank,
        )
        for rank, chunk_id in enumerate(ranked_ids, start=1)
    ]


def _as_retrieved(chunk: TextChunk, **updates) -> RetrievedChunk:
    values = {
        field: getattr(chunk, field)
        for field in TextChunk.__dataclass_fields__
    }
    return RetrievedChunk(**values, **updates)
