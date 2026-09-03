from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import Settings, get_settings
from app.graph.candidate_filter import filter_candidate_chunks
from app.graph.jobs import GraphJobRepository
from app.graph.llm_extractor import (
    GraphExtractionCache,
    create_extraction_batches,
)
from app.graph.progress import ExtractionProgress, GraphProgressStore
from app.graph.semantica_adapter import SemanticaGraphBuilderAdapter
from app.graph.snapshot import GraphSnapshotPipeline
from app.rag.catalog import load_chunk_catalog
from app.rag.index_versions import read_active_pointer, version_directory


@dataclass(frozen=True, slots=True)
class BuildProfile:
    batch_size: int
    batch_chars: int


@dataclass(frozen=True, slots=True)
class BuildPlan:
    index_dir: Path
    index_version: str
    profile: str
    total_chunks: int
    candidate_chunks: int
    cached_chunks: int
    estimated_batches: int
    settings: Settings


PROFILES = {
    "A": BuildProfile(batch_size=2, batch_chars=6000),
    "B": BuildProfile(batch_size=4, batch_chars=8000),
    "C": BuildProfile(batch_size=6, batch_chars=10000),
}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app.graph.cli",
        description="Safe offline candidate graph snapshot builder",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build a non-active candidate graph snapshot")
    build.add_argument("--index-version", required=True)
    build.add_argument("--profile", choices=tuple(PROFILES), default="C")
    build.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    build.add_argument("--model")
    build.add_argument("--dry-run", action="store_true")
    return parser


def create_build_plan(
    settings: Settings,
    *,
    index_version: str,
    profile_name: str,
    workers: int,
    model: str | None,
) -> BuildPlan:
    profile = PROFILES[profile_name]
    effective = settings.model_copy(
        update={
            "graph_extraction_batch_size": profile.batch_size,
            "graph_extraction_batch_chars": profile.batch_chars,
            "graph_extraction_workers": workers,
            **({"graph_extraction_model": model} if model else {}),
        }
    )
    index_dir = version_directory(effective.rag_index_dir, index_version)
    catalog = index_dir / "chunks.jsonl"
    manifest = index_dir / "manifest.json"
    if not index_dir.is_dir() or not catalog.is_file() or not manifest.is_file():
        raise FileNotFoundError(f"candidate index is incomplete: {index_version}")

    chunks = load_chunk_catalog(catalog)
    candidates = filter_candidate_chunks(chunks).candidates
    cache = GraphExtractionCache(effective.graph_snapshot_dir / "cache")
    pending = [
        chunk
        for chunk in candidates
        if cache.read(cache.key(chunk, effective)) is None
    ]
    batches = create_extraction_batches(
        pending,
        effective.graph_extraction_batch_size,
        effective.graph_extraction_batch_chars,
    )
    return BuildPlan(
        index_dir=index_dir,
        index_version=index_version,
        profile=profile_name,
        total_chunks=len(chunks),
        candidate_chunks=len(candidates),
        cached_chunks=len(candidates) - len(pending),
        estimated_batches=len(batches),
        settings=effective,
    )


def print_plan(plan: BuildPlan, *, dry_run: bool) -> None:
    heading = "Graph Build Dry Run" if dry_run else "Graph Build Started"
    print(heading)
    print()
    print(f"Index: {plan.index_version}")
    print(f"Candidates: {plan.candidate_chunks}")
    print(f"Cached: {plan.cached_chunks}")
    print(f"Estimated batches: {plan.estimated_batches}")
    print(
        f"Profile: {plan.profile} "
        f"({plan.settings.graph_extraction_batch_size} chunks / "
        f"{plan.settings.graph_extraction_batch_chars} chars)"
    )
    print(f"Model: {plan.settings.effective_graph_extraction_model}")
    print(f"Workers: {plan.settings.graph_extraction_workers}")
    print(f"Timeout: {_duration(plan.settings.graph_extraction_timeout)}")


async def execute_build(
    plan: BuildPlan,
    *,
    client_factory: Callable[..., AsyncOpenAI] | None = None,
    semantica_factory: Callable[[], SemanticaGraphBuilderAdapter] | None = None,
) -> dict[str, object]:
    settings = plan.settings
    if not settings.graph_build_enabled:
        raise RuntimeError("GRAPH_BUILD_ENABLED must be true")
    if plan.estimated_batches and not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is required for uncached extraction")

    # Fail before any paid extraction if the isolated graph dependency is unavailable.
    semantica = (semantica_factory or SemanticaGraphBuilderAdapter)()
    make_client = client_factory or AsyncOpenAI
    client = (
        make_client(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            timeout=settings.graph_extraction_timeout,
            max_retries=0,
        )
        if plan.estimated_batches
        else None
    )
    jobs = GraphJobRepository(settings.app_database_path)
    signature = _job_signature(plan)
    job = await jobs.enqueue(
        "rebuild",
        {
            "source": "offline-cli",
            "index_version": plan.index_version,
            "profile": plan.profile,
            "workers": settings.graph_extraction_workers,
            "model": settings.effective_graph_extraction_model,
            "timeout": settings.graph_extraction_timeout,
            "activation": False,
        },
        signature=signature,
    )
    await jobs.update(
        job.id,
        status="running",
        stage="extracting",
        progress=0,
        processed_chunks=plan.cached_chunks,
        total_chunks=plan.total_chunks,
        error=None,
    )
    progress_store = GraphProgressStore(settings.graph_snapshot_dir)
    pointer_before = _pointer_bytes(settings.rag_index_dir)

    async def persist(progress: ExtractionProgress) -> None:
        progress_store.write(job.id, progress)
        ratio = progress.processed_chunks / max(progress.candidate_chunks, 1)
        await jobs.update(
            job.id,
            stage="extracting",
            progress=min(ratio * 0.9, 0.9),
            processed_chunks=progress.processed_chunks,
            total_chunks=progress.total_chunks,
        )
        _print_progress(progress)

    pointer = read_active_pointer(settings.rag_index_dir)
    parent_graph_version = (
        pointer.get("graph_version")
        if pointer.get("index_version") == plan.index_version
        else None
    )
    pipeline = GraphSnapshotPipeline(settings, client, semantica=semantica)
    try:
        metadata = await pipeline.build_for_index(
            plan.index_dir,
            plan.index_version,
            parent_graph_version=parent_graph_version,
            force_reextract=False,
            mode="offline-candidate",
            progress_callback=persist,
        )
        if _pointer_bytes(settings.rag_index_dir) != pointer_before:
            raise RuntimeError("active pointer changed during offline graph build")
        await jobs.update(
            job.id,
            status="completed",
            stage="completed",
            progress=1,
            processed_chunks=plan.candidate_chunks,
            total_chunks=plan.total_chunks,
            result_graph_version=str(metadata["graph_version"]),
            result_index_version=plan.index_version,
            lease_expires_at=None,
        )
        return metadata
    except BaseException as exc:
        await jobs.update(
            job.id,
            status="failed",
            stage="failed",
            error=_safe_error(exc),
            lease_expires_at=None,
        )
        raise
    finally:
        if client is not None:
            await client.close()


def main(argv: Sequence[str] | None = None, *, settings: Settings | None = None) -> None:
    args = create_parser().parse_args(argv)
    effective_settings = settings or get_settings()
    if args.command != "build":
        raise AssertionError("unreachable command")
    plan = create_build_plan(
        effective_settings,
        index_version=args.index_version,
        profile_name=args.profile,
        workers=args.workers,
        model=args.model,
    )
    print_plan(plan, dry_run=args.dry_run)
    if args.dry_run:
        print()
        print("Dry run completed. No LLM request or snapshot build was performed.")
        return

    metadata = asyncio.run(execute_build(plan))
    graph_version = str(metadata["graph_version"])
    print()
    print("Build completed.")
    print()
    print("Candidate graph snapshot created:")
    print(f"{settings_path(plan.settings.graph_snapshot_dir)}/versions/{graph_version}")
    print()
    print("Activation requires manual approval.")


def settings_path(path: Path) -> str:
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            return path.name
    return path.as_posix().rstrip("/")


def _job_signature(plan: BuildPlan) -> str:
    values = {
        "index_version": plan.index_version,
        "model": plan.settings.effective_graph_extraction_model,
        "profile": plan.profile,
        "batch_size": plan.settings.graph_extraction_batch_size,
        "batch_chars": plan.settings.graph_extraction_batch_chars,
        "workers": plan.settings.graph_extraction_workers,
        "timeout": plan.settings.graph_extraction_timeout,
        "prompt": plan.settings.graph_extraction_prompt_version,
        "validator": plan.settings.graph_validator_version,
    }
    digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return f"offline-build:{digest}"


def _pointer_bytes(index_root: Path) -> bytes | None:
    path = index_root / "active.json"
    return path.read_bytes() if path.is_file() else None


def _print_progress(progress: ExtractionProgress) -> None:
    print()
    print("Progress:")
    print(f"processed: {progress.processed_chunks}/{progress.candidate_chunks}")
    print(f"success: {progress.success_count}")
    print(f"failed: {progress.failed_count}")
    print(f"cached: {progress.cached_chunks}")
    eta = (
        _duration(progress.estimated_remaining_seconds)
        if progress.estimated_remaining_seconds is not None
        else "calculating"
    )
    print(f"ETA: {eta}")


def _duration(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _safe_error(exc: BaseException) -> str:
    value = f"{type(exc).__name__}: {exc}"
    value = re.sub(
        r"(?i)(authorization|api[_-]?key)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        value,
    )
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[redacted]", value)
    return value[:500]


if __name__ == "__main__":
    main()
