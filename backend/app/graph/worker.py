from __future__ import annotations

import argparse
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from openai import AsyncOpenAI

from app.core.config import Settings, get_settings
from app.graph.jobs import GraphJob, GraphJobRepository
from app.graph.progress import ExtractionProgress, GraphProgressStore
from app.graph.snapshot import GraphSnapshotPipeline
from app.knowledge_gap.repository import SqliteKnowledgeGapRepository
from app.rag.catalog import load_chunk_catalog
from app.rag.index_versions import read_active_pointer, resolve_active_index
from app.rag.service import RagService
from app.services.knowledge_gap_review_service import KnowledgeGapReviewService

LOGGER = logging.getLogger(__name__)


class GraphWorker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jobs = GraphJobRepository(settings.app_database_path)
        self.client = (
            AsyncOpenAI(
                api_key=settings.dashscope_api_key,
                base_url=settings.dashscope_base_url,
                timeout=settings.graph_extraction_timeout,
                max_retries=0,
            )
            if settings.dashscope_api_key
            else None
        )
        self.pipeline = GraphSnapshotPipeline(settings, self.client)
        repository = SqliteKnowledgeGapRepository(settings.app_database_path)
        self.review = KnowledgeGapReviewService(
            settings,
            repository,
            RagService.from_settings(settings),
        )

    async def run_once(self) -> bool:
        job = await self.jobs.claim(self.settings.graph_worker_lease_seconds)
        if job is None:
            return False
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        try:
            if job.kind == "rebuild":
                await self._rebuild(job)
            else:
                await self._publish(job)
        except Exception as exc:
            LOGGER.exception("graph job failed: %s", job.id)
            await self.jobs.update(
                job.id,
                status="failed",
                stage="failed",
                error=_safe_error(exc),
                lease_expires_at=None,
            )
            if job.kind == "publish":
                try:
                    await self.review.restore_publish_failure(
                        str(job.payload["gap_id"]),
                        version=int(job.payload["version"]),
                        actor="graph-worker",
                    )
                except Exception:
                    LOGGER.exception("could not restore publishing gap: %s", job.id)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        return True

    async def _heartbeat(self, job_id: str) -> None:
        interval = max(20, self.settings.graph_worker_lease_seconds // 3)
        while True:
            await asyncio.sleep(interval)
            expires = datetime.now(timezone.utc) + timedelta(
                seconds=self.settings.graph_worker_lease_seconds
            )
            await self.jobs.update(job_id, lease_expires_at=expires)

    async def _rebuild(self, job: GraphJob) -> None:
        index_dir, index_version = resolve_active_index(self.settings.rag_index_dir)
        pointer = read_active_pointer(self.settings.rag_index_dir)
        total_chunks = len(load_chunk_catalog(index_dir / "chunks.jsonl"))
        await self.jobs.update(
            job.id,
            stage="extracting",
            progress=0.1,
            total_chunks=total_chunks,
        )

        progress_store = GraphProgressStore(self.settings.graph_snapshot_dir)

        async def persist(progress: ExtractionProgress) -> None:
            progress_store.write(job.id, progress)
            extraction_progress = 0.1 + 0.8 * (
                progress.processed_chunks / max(progress.candidate_chunks, 1)
            )
            await self.jobs.update(
                job.id,
                stage="extracting",
                progress=min(extraction_progress, 0.9),
                processed_chunks=progress.processed_chunks,
                total_chunks=progress.total_chunks,
            )

        metadata = await self.pipeline.build_for_index(
            index_dir,
            index_version,
            parent_graph_version=pointer.get("graph_version"),
            force_reextract=bool(job.payload.get("force_reextract")),
            mode=str(job.payload.get("mode", "incremental")),
            progress_callback=persist,
        )
        graph_version = str(metadata["graph_version"])
        await self.jobs.update(
            job.id,
            status="completed",
            stage="completed",
            progress=1,
            processed_chunks=int(metadata["source_chunks"]),
            total_chunks=int(metadata["source_chunks"]),
            result_graph_version=graph_version,
            result_index_version=index_version,
            lease_expires_at=None,
        )

    async def _publish(self, job: GraphJob) -> None:
        await self.jobs.update(job.id, stage="publishing", progress=0.05)
        published = await self.review.publish(
            str(job.payload["gap_id"]),
            version=int(job.payload["version"]),
            actor=str(job.payload.get("actor", "graph-worker")),
            graph_pipeline=self.pipeline,
        )
        pointer = read_active_pointer(self.settings.rag_index_dir)
        await self.jobs.update(
            job.id,
            status="completed",
            stage="completed",
            progress=1,
            result_graph_version=pointer.get("graph_version"),
            result_index_version=pointer.get("index_version"),
            lease_expires_at=None,
        )
        LOGGER.info("published knowledge gap %s", published.id)

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()


async def _run(once: bool) -> None:
    worker = GraphWorker(get_settings())
    try:
        while True:
            worked = await worker.run_once()
            if once:
                return
            if not worked:
                await asyncio.sleep(worker.settings.graph_worker_poll_seconds)
    finally:
        await worker.close()


def _safe_error(exc: Exception) -> str:
    value = f"{type(exc).__name__}: {exc}"
    value = re.sub(
        r"(?i)(authorization|api[_-]?key)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        value,
    )
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[redacted]", value)
    return value[:500]


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge graph worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run(args.once))


if __name__ == "__main__":
    main()
