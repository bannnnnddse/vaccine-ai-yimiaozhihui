from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from app.core.config import Settings
from app.graph.cli import create_build_plan, execute_build, main
from app.graph.llm_extractor import (
    GraphExtractionCache,
    LLMBatchExtraction,
    LLMGraphExtractor,
    ValidatedChunkExtraction,
)
from app.rag.catalog import write_chunk_catalog
from app.rag.index_versions import version_directory
from app.rag.models import TextChunk


def _chunk(index: int) -> TextChunk:
    return TextChunk(
        id=f"chunk-{index}",
        file_name="test.md",
        relative_path="test.md",
        page=None,
        chunk_index=index,
        text=f"乙肝疫苗可预防乙型肝炎，建议目标人群按程序接种第 {index + 1} 剂。",
        source_hash="source",
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        dashscope_api_key="test-key",
        rag_index_dir=tmp_path / "rag-index",
        graph_snapshot_dir=tmp_path / "graph",
        app_database_path=tmp_path / "runtime" / "app.db",
    )


def _write_index(settings: Settings, version: str, count: int = 3) -> Path:
    index_dir = version_directory(settings.rag_index_dir, version)
    write_chunk_catalog(index_dir / "chunks.jsonl", [_chunk(index) for index in range(count)])
    (index_dir / "manifest.json").write_text("{}", encoding="utf-8")
    return index_dir


class _Semantica:
    def build(self, entities, relationships):
        return {"entities": entities, "relationships": relationships}


class _Client:
    async def close(self) -> None:
        return None


def _client_factory(**_kwargs):
    return _Client()


def test_dry_run_selects_profile_without_calling_llm(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    settings = _settings(tmp_path)
    _write_index(settings, "rag-v2-dry-run")

    async def forbidden_request(self, chunks):
        raise AssertionError("dry-run must not call the LLM")

    monkeypatch.setattr(LLMGraphExtractor, "_request_batch", forbidden_request)
    main(
        [
            "build",
            "--index-version",
            "rag-v2-dry-run",
            "--profile",
            "B",
            "--workers",
            "4",
            "--model",
            "qwen3.8-max",
            "--dry-run",
        ],
        settings=settings,
    )

    output = capsys.readouterr().out
    assert "Graph Build Dry Run" in output
    assert "Profile: B" in output
    assert "Model: qwen3.8-max" in output
    assert "Workers: 4" in output
    assert not settings.app_database_path.exists()
    assert not (settings.graph_snapshot_dir / "versions").exists()


def test_build_creates_candidate_snapshot_without_changing_active_pointer(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    version = "rag-v2-safety"
    _write_index(settings, version, count=2)
    settings.rag_index_dir.mkdir(parents=True, exist_ok=True)
    active = settings.rag_index_dir / "active.json"
    original = {"index_version": "rag-v2-existing", "graph_version": "graph-existing"}
    active.write_text(json.dumps(original), encoding="utf-8")

    async def empty_response(self, chunks):
        return LLMBatchExtraction()

    monkeypatch.setattr(LLMGraphExtractor, "_request_batch", empty_response)
    plan = create_build_plan(
        settings,
        index_version=version,
        profile_name="C",
        workers=2,
        model="qwen3.8-max",
    )
    metadata = asyncio.run(
        execute_build(
            plan,
            client_factory=_client_factory,
            semantica_factory=lambda: _Semantica(),
        )
    )

    assert json.loads(active.read_text(encoding="utf-8")) == original
    snapshot = settings.graph_snapshot_dir / "versions" / str(metadata["graph_version"])
    assert (snapshot / "metadata.json").is_file()
    assert metadata["knowledge_base_version"] == version
    assert metadata["build_mode"] == "offline-candidate"


def test_resume_build_only_requests_chunks_missing_from_cache(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    version = "rag-v2-resume"
    _write_index(settings, version, count=3)
    plan = create_build_plan(
        settings,
        index_version=version,
        profile_name="A",
        workers=2,
        model="qwen3.8-flash",
    )
    first = _chunk(0)
    cache = GraphExtractionCache(plan.settings.graph_snapshot_dir / "cache")
    cache.write(
        cache.key(first, plan.settings),
        ValidatedChunkExtraction(
            chunk_id=first.id,
            content_hash=hashlib.sha256(first.text.encode()).hexdigest(),
        ),
    )
    requested: list[str] = []

    async def record_request(self, chunks):
        requested.extend(chunk.id for chunk in chunks)
        return LLMBatchExtraction()

    monkeypatch.setattr(LLMGraphExtractor, "_request_batch", record_request)
    resumed_plan = create_build_plan(
        settings,
        index_version=version,
        profile_name="A",
        workers=2,
        model="qwen3.8-flash",
    )
    assert resumed_plan.cached_chunks == 1
    asyncio.run(
        execute_build(
            resumed_plan,
            client_factory=_client_factory,
            semantica_factory=lambda: _Semantica(),
        )
    )

    assert set(requested) == {"chunk-1", "chunk-2"}
    assert "chunk-0" not in requested
    progress_files = list((settings.graph_snapshot_dir / "progress").glob("*.json"))
    assert len(progress_files) == 1
    progress = json.loads(progress_files[0].read_text(encoding="utf-8"))
    assert progress["processed_chunks"] == 3
    assert progress["cached_chunks"] == 1
