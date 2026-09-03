"""Deterministic, offline-safe selection for GraphRAG benchmark samples."""

from __future__ import annotations

import random

from app.graph.candidate_filter import filter_candidate_chunks
from app.rag.models import TextChunk

FIXED_BENCHMARK_SAMPLE_SIZE = 100
FIXED_BENCHMARK_SEED = 20260820


def fixed_benchmark_sample(chunks: list[TextChunk]) -> list[TextChunk]:
    """Select the same 100 source chunks for all profiles and future runs."""

    return random.Random(FIXED_BENCHMARK_SEED).sample(
        chunks, min(FIXED_BENCHMARK_SAMPLE_SIZE, len(chunks))
    )


def benchmark_candidate_count(chunks: list[TextChunk]) -> int:
    """Return the optimized experiment's input count without invoking an LLM."""

    return filter_candidate_chunks(chunks).candidate_count
