"""Durable, atomic progress snapshots for long-running graph extraction."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExtractionProgress:
    total_chunks: int
    candidate_chunks: int
    processed_chunks: int
    cached_chunks: int
    success_count: int
    failed_count: int
    elapsed_seconds: float
    estimated_remaining_seconds: float | None
    failed_chunk_ids: tuple[str, ...] = ()


class ProgressTracker:
    def __init__(self, total_chunks: int, candidate_chunks: int) -> None:
        self.total_chunks = total_chunks
        self.candidate_chunks = candidate_chunks
        self.cached_chunks = 0
        self.success_count = 0
        self.failed_chunk_ids: list[str] = []
        self._started = time.monotonic()

    def cached(self, count: int) -> ExtractionProgress:
        self.cached_chunks = count
        return self.snapshot()

    def completed(self, successful: int, failed_ids: list[str]) -> ExtractionProgress:
        self.success_count += successful
        self.failed_chunk_ids.extend(failed_ids)
        return self.snapshot()

    def snapshot(self) -> ExtractionProgress:
        elapsed = time.monotonic() - self._started
        processed = self.cached_chunks + self.success_count + len(self.failed_chunk_ids)
        rate = processed / elapsed if elapsed > 0 and processed else 0
        remaining = self.candidate_chunks - processed
        return ExtractionProgress(
            total_chunks=self.total_chunks,
            candidate_chunks=self.candidate_chunks,
            processed_chunks=processed,
            cached_chunks=self.cached_chunks,
            success_count=self.success_count,
            failed_count=len(self.failed_chunk_ids),
            elapsed_seconds=round(elapsed, 3),
            estimated_remaining_seconds=round(remaining / rate, 3) if rate else None,
            failed_chunk_ids=tuple(sorted(set(self.failed_chunk_ids))),
        )


class GraphProgressStore:
    def __init__(self, root: Path) -> None:
        self.root = root / "progress"

    def write(self, job_id: str, progress: ExtractionProgress) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{job_id}.json"
        temporary = path.with_suffix(".tmp")
        payload = {**asdict(progress), "updated_at": datetime.now(timezone.utc).isoformat()}
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return path
