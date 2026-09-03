"""Offline-safe measurement harness for graph-extraction batch experiments.

The harness receives an injected batch request function. Tests use local
fixtures; a future explicitly authorised run may inject a production request.
It never activates a graph version or writes cache/snapshot data.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import ValidationError

from app.graph.llm_extractor import LLMBatchExtraction, create_extraction_batches, validate_batch
from app.rag.models import TextChunk

BatchRequest = Callable[[list[TextChunk]], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class BatchBenchmarkProfile:
    name: str
    batch_size: int
    batch_chars: int
    timeout_seconds: float


BATCH_BENCHMARK_PROFILES: tuple[BatchBenchmarkProfile, ...] = (
    BatchBenchmarkProfile("A", batch_size=2, batch_chars=6000, timeout_seconds=180),
    BatchBenchmarkProfile("B", batch_size=4, batch_chars=8000, timeout_seconds=180),
    BatchBenchmarkProfile("C", batch_size=6, batch_chars=10000, timeout_seconds=180),
)


@dataclass(frozen=True, slots=True)
class BatchBenchmarkMetrics:
    profile: BatchBenchmarkProfile
    batches: int
    processed_chunks: int
    total_latency_seconds: float
    average_latency_seconds: float
    timeout_count: int
    json_validation_failure_count: int
    request_failure_count: int
    rejected_candidate_count: int
    accepted_medical_relation_count: int


async def benchmark_profile(
    chunks: list[TextChunk],
    profile: BatchBenchmarkProfile,
    request_batch: BatchRequest,
    *,
    min_confidence: float,
) -> BatchBenchmarkMetrics:
    """Measure one profile while preserving the production validator boundary."""

    batches = create_extraction_batches(chunks, profile.batch_size, profile.batch_chars)
    latency: list[float] = []
    processed = timeouts = json_failures = request_failures = rejected = accepted = 0
    for batch in batches:
        started = time.perf_counter()
        try:
            raw = await asyncio.wait_for(request_batch(batch), timeout=profile.timeout_seconds)
            payload = LLMBatchExtraction.model_validate_json(raw)
        except TimeoutError:
            timeouts += 1
            latency.append(time.perf_counter() - started)
            continue
        except ValidationError:
            json_failures += 1
            latency.append(time.perf_counter() - started)
            continue
        except Exception:
            request_failures += 1
            latency.append(time.perf_counter() - started)
            continue
        latency.append(time.perf_counter() - started)
        validated = validate_batch(payload, batch, min_confidence)
        processed += len(batch)
        rejected += sum(len(item.rejected) for item in validated)
        accepted += sum(len(item.relations) for item in validated)
    total = sum(latency)
    return BatchBenchmarkMetrics(
        profile=profile,
        batches=len(batches),
        processed_chunks=processed,
        total_latency_seconds=total,
        average_latency_seconds=total / len(latency) if latency else 0,
        timeout_count=timeouts,
        json_validation_failure_count=json_failures,
        request_failure_count=request_failures,
        rejected_candidate_count=rejected,
        accepted_medical_relation_count=accepted,
    )
