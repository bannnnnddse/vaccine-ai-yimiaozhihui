#!/usr/bin/env python3
"""RAG V2 formal retrieval evaluation runner.

Stages:
  validate   Pre-flight checks on the frozen 1000-case set (counts, duplicates,
             gold existence in the ACTIVE index, difficulty distribution) and
             hash/config freezing into config_snapshot.json.
  run        ONE formal retrieval pass of all 1000 cases through the real
             production Hybrid RAG retriever:
                 RagService.retrieve_with_trace()
                   = Dense (NumpyRagStore/BgeEmbedder)
                   + BM25 (Bm25Index)
                   + RRF (reciprocal_rank_fusion)
                   + CrossEncoder rerank (CrossEncoderReranker)
                   + quality prior + diversity selection -> Top-4
             It never touches POST /api/v1/chat, QwenService answer
             generation, evidence assessment, PubMed or Knowledge Gap.
             raw_results.jsonl keeps every case including misses; checkpoint
             append is only for crash recovery, never for resampling.
  summarize  Computes metrics from raw_results.jsonl only, writes
             summary.json and failure_cases.jsonl with deterministic
             failure-type classification (see methodology.md).

This script never invents metrics and never modifies retrieval parameters.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

OUT_DIR = REPO_ROOT / "docs" / "evaluation" / "rag_v2"
CASES_PATH = OUT_DIR / "evaluation_cases.jsonl"
GOLD_PATH = OUT_DIR / "gold_labels.jsonl"
RAW_PATH = OUT_DIR / "raw_results.jsonl"
TRACES_PATH = OUT_DIR / "raw_traces.jsonl"
FAILURES_PATH = OUT_DIR / "failure_cases.jsonl"
SUMMARY_PATH = OUT_DIR / "summary.json"
CONFIG_PATH = OUT_DIR / "config_snapshot.json"
FREEZE_PATH = OUT_DIR / "freeze_manifest.json"
METRIC_PATH = OUT_DIR / "metric_definition.json"
RUN_STATE_PATH = OUT_DIR / "formal_run_state.json"
CHECKPOINT_PATH = OUT_DIR / "formal_checkpoint.json"
INVALID_RUNS_PATH = OUT_DIR / "invalid_runs.jsonl"

FINAL_TOTAL = 1000
QUOTA_TOLERANCE = 0.05  # 55/35/10 +/- 5 percentage points
METRIC_DEFINITION = {
    "name": "rag_v2_top_k_chunk_recall",
    "version": 1,
    "unit": "case",
    "top_k": 4,
    "hit_rule": (
        "A case is a Top-4 hit iff at least one chunk_id among the first four "
        "selected production results belongs to acceptable_gold_chunk_ids."
    ),
    "top1_rule": "A case is a Top-1 hit iff the first selected chunk is acceptable gold.",
    "mrr_rule": (
        "Mean reciprocal rank of the first acceptable gold chunk within Top-4; "
        "misses contribute 0."
    ),
    "error_rule": (
        "Any retrieval exception invalidates the formal run; failed cases are never filtered."
    ),
}
FROZEN_SOURCE_PATHS = (
    Path("backend/app/core/config.py"),
    Path("backend/app/rag/hybrid.py"),
    Path("backend/app/rag/ranking.py"),
    Path("backend/app/rag/reranker.py"),
    Path("backend/app/rag/service.py"),
    Path("scripts/evaluate_rag_v2.py"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def atomic_write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    temporary.replace(path)


def append_jsonl_sync(path: Path, value: object) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(value, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def source_hashes() -> dict[str, str]:
    return {path.as_posix(): sha256_file(REPO_ROOT / path) for path in FROZEN_SOURCE_PATHS}


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True, encoding="utf-8"
        ).strip()
    except Exception:  # noqa: BLE001
        return "not_available"


def frozen_sources_are_clean() -> bool:
    command = ["git", "diff", "--quiet", "HEAD", "--", *map(str, FROZEN_SOURCE_PATHS)]
    unstaged = subprocess.run(command, cwd=str(REPO_ROOT), check=False).returncode == 0
    command.insert(2, "--cached")
    staged = subprocess.run(command, cwd=str(REPO_ROOT), check=False).returncode == 0
    return unstaged and staged


def active_index_info(settings) -> tuple[str, str, dict]:
    from app.rag.index_versions import resolve_active_index

    active_path, active_version = resolve_active_index(settings.rag_index_dir)
    manifest = json.loads((active_path / "manifest.json").read_text(encoding="utf-8"))
    return active_path, active_version, manifest


def index_hashes(active_path: Path) -> dict[str, str]:
    names = ("manifest.json", "chunks.jsonl", "vectors.npy")
    return {name: sha256_file(active_path / name) for name in names}


def pipeline_settings(settings) -> dict:
    return {
        "rag_pipeline": settings.rag_pipeline,
        "rag_top_k": settings.rag_top_k,
        "rag_dense_fetch_k": settings.rag_dense_fetch_k,
        "rag_lexical_fetch_k": settings.rag_lexical_fetch_k,
        "rag_rrf_k": settings.rag_rrf_k,
        "rag_bm25_k1": settings.rag_bm25_k1,
        "rag_bm25_b": settings.rag_bm25_b,
        "rag_fusion_candidate_k": settings.rag_fusion_candidate_k,
        "rag_rerank_candidate_k": settings.rag_rerank_candidate_k,
        "rag_reranker_enabled": settings.rag_reranker_enabled,
        "rag_reranker_batch_size": settings.rag_reranker_batch_size,
        "rag_reranker_max_length": settings.rag_reranker_max_length,
        "rag_min_relevance": settings.rag_min_relevance,
        "rag_min_similarity": settings.rag_min_similarity,
        "rag_max_chunks_per_document": settings.rag_max_chunks_per_document,
        "rag_near_duplicate_threshold": settings.rag_near_duplicate_threshold,
        "rag_quality_prior_max_adjustment": settings.rag_quality_prior_max_adjustment,
        "rag_quality_authority_share": settings.rag_quality_authority_share,
        "rag_freshness_max_adjustment": settings.rag_freshness_max_adjustment,
        "rag_embedding_model": settings.rag_embedding_model,
        "rag_reranker_model": settings.rag_reranker_model,
        "rag_chunk_size": settings.rag_chunk_size,
        "rag_chunk_overlap": settings.rag_chunk_overlap,
        "rag_window_rescore_enabled": settings.rag_window_rescore_enabled,
        "rag_window_reranker_max_length": settings.rag_window_reranker_max_length,
        "rag_window_prev_chars": settings.rag_window_prev_chars,
        "rag_window_next_chars": settings.rag_window_next_chars,
        "rag_window_reranker_batch_size": settings.rag_window_reranker_batch_size,
        "rag_neighbor_smooth_lambda": settings.rag_neighbor_smooth_lambda,
    }


def cmd_validate() -> None:
    cases = load_jsonl(CASES_PATH)
    gold = load_jsonl(GOLD_PATH)
    errors: list[str] = []

    if len(cases) != FINAL_TOTAL:
        errors.append(f"expected {FINAL_TOTAL} cases, got {len(cases)}")
    ids = [c["case_id"] for c in cases]
    expected_ids = [f"RAGV2-{i:04d}" for i in range(1, len(cases) + 1)]
    if ids != expected_ids:
        errors.append("case_id sequence is not RAGV2-0001..RAGV2-1000")
    if len(set(ids)) != len(ids):
        errors.append("duplicate case_id")
    questions = [c["question"] for c in cases]
    if len(set(questions)) != len(questions):
        errors.append("duplicate question text")

    diff_counts = Counter(c["difficulty"] for c in cases)
    for diff, target in (("easy", 0.55), ("medium", 0.35), ("hard", 0.10)):
        share = diff_counts.get(diff, 0) / max(len(cases), 1)
        if abs(share - target) > QUOTA_TOLERANCE:
            errors.append(
                f"difficulty {diff} share {share:.2%} outside tolerance for target {target:.0%}"
            )

    gold_by_case = {g["case_id"]: g for g in gold}
    if set(gold_by_case) != set(ids):
        errors.append("gold_labels case ids do not match evaluation_cases")

    settings = _get_settings()
    active_path, active_version, manifest = active_index_info(settings)
    if METRIC_PATH.exists():
        if json.loads(METRIC_PATH.read_text(encoding="utf-8")) != METRIC_DEFINITION:
            errors.append("metric_definition.json differs from the evaluator's frozen definition")
    else:
        errors.append("metric_definition.json missing")
    if not frozen_sources_are_clean():
        errors.append("frozen production/evaluator sources differ from HEAD; commit them first")
    stale_outputs = [
        path.name
        for path in (
            RAW_PATH,
            TRACES_PATH,
            FAILURES_PATH,
            SUMMARY_PATH,
            RUN_STATE_PATH,
            CHECKPOINT_PATH,
        )
        if path.exists()
    ]
    if stale_outputs:
        errors.append(f"formal output paths are not clean: {stale_outputs}")
    chunk_ids: set[str] = set()
    doc_ids: set[str] = set()
    with (active_path / "chunks.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                chunk = json.loads(line)
                chunk_ids.add(chunk["id"])
                doc_ids.add(chunk["parent_doc_id"])

    missing_gold = 0
    missing_doc = 0
    for case in cases:
        entry = gold_by_case.get(case["case_id"], {})
        acceptable = (
            entry.get("acceptable_gold_chunk_ids") or case.get("acceptable_gold_chunk_ids") or []
        )
        if not case.get("gold_chunk_ids") or not acceptable:
            errors.append(f"{case['case_id']}: empty gold")
            missing_gold += 1
            continue
        if not set(acceptable) <= chunk_ids:
            errors.append(f"{case['case_id']}: gold chunk not found in active index")
            missing_gold += 1
        if not set(case.get("gold_source_ids") or []) <= doc_ids:
            errors.append(f"{case['case_id']}: gold source doc not found in active index")
            missing_doc += 1

    if errors:
        print("VALIDATION FAILED:")
        for err in errors[:20]:
            print(" -", err)
        raise SystemExit(1)

    snapshot = {
        "frozen_at_utc": utc_now(),
        "git_commit": git_commit(),
        "index_version": active_version,
        "index_manifest": {
            "embedding_model": manifest["embedding_model"],
            "dense_backend": manifest["dense_backend"],
            "chunking_version": manifest["chunking_version"],
            "chunk_size": manifest["chunk_size"],
            "chunk_overlap": manifest["chunk_overlap"],
            "corpus_manifest_hash": manifest["corpus_manifest_hash"],
            "chunk_catalog_hash": manifest["chunk_catalog_hash"],
            "chunk_count": manifest["chunk_count"],
            "document_count": manifest["document_count"],
        },
        "retrieval_settings": pipeline_settings(settings),
        "metric_definition": METRIC_DEFINITION,
        "source_hashes": source_hashes(),
        "index_file_hashes": index_hashes(active_path),
        "hashes": {
            "evaluation_cases_sha256": sha256_file(CASES_PATH),
            "gold_labels_sha256": sha256_file(GOLD_PATH),
            "metric_definition_sha256": sha256_file(METRIC_PATH),
            "corpus_manifest_sha256": sha256_file(settings.rag_corpus_manifest_path),
            "retrieval_settings_sha256": canonical_sha256(pipeline_settings(settings)),
        },
    }
    atomic_write_json(CONFIG_PATH, snapshot)
    freeze = {
        "frozen_at_utc": snapshot["frozen_at_utc"],
        "git_commit": snapshot["git_commit"],
        "config_snapshot_sha256": sha256_file(CONFIG_PATH),
        "evaluation_script_sha256": snapshot["source_hashes"]["scripts/evaluate_rag_v2.py"],
        "metric_definition_sha256": snapshot["hashes"]["metric_definition_sha256"],
        "evaluation_cases_sha256": snapshot["hashes"]["evaluation_cases_sha256"],
        "gold_labels_sha256": snapshot["hashes"]["gold_labels_sha256"],
        "corpus_manifest_sha256": snapshot["hashes"]["corpus_manifest_sha256"],
        "retrieval_settings_sha256": snapshot["hashes"]["retrieval_settings_sha256"],
        "index_version": active_version,
        "index_file_hashes": snapshot["index_file_hashes"],
    }
    atomic_write_json(FREEZE_PATH, freeze)
    print(f"VALIDATION OK: {len(cases)} cases; difficulty={dict(diff_counts)}")
    print(f"config snapshot -> {CONFIG_PATH}")
    print(f"freeze manifest -> {FREEZE_PATH}")


def _get_settings():
    from app.core.config import get_settings

    return get_settings()


def _verify_frozen_config(settings) -> None:
    if not CONFIG_PATH.exists() or not FREEZE_PATH.exists():
        raise SystemExit("freeze files missing; run validate first")
    snapshot = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    if sha256_file(CONFIG_PATH) != freeze["config_snapshot_sha256"]:
        raise SystemExit("config_snapshot.json changed since freeze; refusing to run")
    if git_commit() != snapshot["git_commit"]:
        raise SystemExit("HEAD changed since freeze; refusing to run")
    if not frozen_sources_are_clean():
        raise SystemExit("frozen sources differ from HEAD; refusing to run")
    current = pipeline_settings(settings)
    if current != snapshot["retrieval_settings"]:
        diff = {
            k: (snapshot["retrieval_settings"].get(k), current.get(k))
            for k in set(current) | set(snapshot["retrieval_settings"])
            if current.get(k) != snapshot["retrieval_settings"].get(k)
        }
        raise SystemExit(f"RAG settings changed since freeze; refusing to run. diff={diff}")
    if sha256_file(CASES_PATH) != snapshot["hashes"]["evaluation_cases_sha256"]:
        raise SystemExit("evaluation_cases.jsonl changed since freeze; refusing to run")
    if sha256_file(GOLD_PATH) != snapshot["hashes"]["gold_labels_sha256"]:
        raise SystemExit("gold_labels.jsonl changed since freeze; refusing to run")
    if sha256_file(METRIC_PATH) != snapshot["hashes"]["metric_definition_sha256"]:
        raise SystemExit("metric_definition.json changed since freeze; refusing to run")
    if json.loads(METRIC_PATH.read_text(encoding="utf-8")) != METRIC_DEFINITION:
        raise SystemExit("metric definition differs from evaluator; refusing to run")
    if (
        sha256_file(settings.rag_corpus_manifest_path)
        != snapshot["hashes"]["corpus_manifest_sha256"]
    ):
        raise SystemExit("corpus manifest changed since freeze; refusing to run")
    current_sources = source_hashes()
    if current_sources != snapshot["source_hashes"]:
        raise SystemExit("production/evaluator source hashes changed since freeze; refusing to run")
    active_path, active_version, manifest = active_index_info(settings)
    if active_version != snapshot["index_version"]:
        raise SystemExit("active index version changed since freeze; refusing to run")
    if index_hashes(active_path) != snapshot["index_file_hashes"]:
        raise SystemExit("active index files changed since freeze; refusing to run")
    if manifest["corpus_manifest_hash"] != snapshot["index_manifest"]["corpus_manifest_hash"]:
        raise SystemExit("index corpus hash changed since freeze; refusing to run")


def _new_run_state() -> dict:
    if RAW_PATH.exists() or TRACES_PATH.exists():
        raise SystemExit("formal artifacts already exist without an active run state")
    snapshot = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    run_id = f"formal-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{snapshot['git_commit'][:8]}"
    state = {
        "run_id": run_id,
        "status": "running",
        "started_at_utc": utc_now(),
        "updated_at_utc": utc_now(),
        "git_commit": snapshot["git_commit"],
        "index_version": snapshot["index_version"],
        "freeze_manifest_sha256": sha256_file(FREEZE_PATH),
    }
    atomic_write_json(RUN_STATE_PATH, state)
    atomic_write_json(
        CHECKPOINT_PATH,
        {
            "run_id": run_id,
            "completed_cases": 0,
            "last_case_id": None,
            "raw_results_size": 0,
            "raw_traces_size": 0,
            "updated_at_utc": utc_now(),
        },
    )
    return state


def _load_running_state() -> dict:
    if not RUN_STATE_PATH.exists():
        return _new_run_state()
    state = json.loads(RUN_STATE_PATH.read_text(encoding="utf-8"))
    if state.get("status") != "running":
        raise SystemExit(
            f"formal run {state.get('run_id')} has status={state.get('status')}; "
            "archive it before starting another run"
        )
    if state.get("freeze_manifest_sha256") != sha256_file(FREEZE_PATH):
        raise SystemExit("freeze manifest differs from active formal run")
    return state


def _load_resume_records(state: dict) -> tuple[list[dict], list[dict]]:
    results = load_jsonl(RAW_PATH) if RAW_PATH.exists() else []
    traces = load_jsonl(TRACES_PATH) if TRACES_PATH.exists() else []
    result_ids = [row.get("case_id") for row in results]
    trace_ids = [row.get("case_id") for row in traces]
    if result_ids != trace_ids or len(set(result_ids)) != len(result_ids):
        _mark_invalid(state, "checkpoint artifact case IDs are missing, duplicated, or misaligned")
        raise SystemExit("formal artifacts are inconsistent; run marked invalid")
    if CHECKPOINT_PATH.exists():
        checkpoint = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        if checkpoint.get("run_id") != state["run_id"]:
            _mark_invalid(state, "checkpoint belongs to a different run")
            raise SystemExit("checkpoint run_id mismatch; run marked invalid")
        if checkpoint.get("completed_cases") != len(results):
            _mark_invalid(state, "checkpoint count differs from durable artifacts")
            raise SystemExit("checkpoint count mismatch; run marked invalid")
    return results, traces


def _mark_invalid(state: dict, reason: str) -> None:
    record = {
        "run_id": state.get("run_id"),
        "invalidated_at_utc": utc_now(),
        "reason": reason,
        "completed_cases": len(load_jsonl(RAW_PATH)) if RAW_PATH.exists() else 0,
        "freeze_manifest_sha256": state.get("freeze_manifest_sha256"),
    }
    append_jsonl_sync(INVALID_RUNS_PATH, record)
    state = {**state, "status": "invalid", "updated_at_utc": utc_now(), "invalid_reason": reason}
    atomic_write_json(RUN_STATE_PATH, state)


def _write_checkpoint(state: dict, case_id: str, completed_cases: int) -> None:
    atomic_write_json(
        CHECKPOINT_PATH,
        {
            "run_id": state["run_id"],
            "completed_cases": completed_cases,
            "last_case_id": case_id,
            "raw_results_size": RAW_PATH.stat().st_size,
            "raw_traces_size": TRACES_PATH.stat().st_size,
            "updated_at_utc": utc_now(),
        },
    )


def cmd_run(limit: int | None) -> None:
    settings = _get_settings()
    _verify_frozen_config(settings)

    from app.rag.service import RagService

    _, active_version, _ = active_index_info(settings)
    service = RagService.for_index_version(settings, active_version)
    print(f"[run] active index: {active_version}")
    trace = service.warmup()
    if trace.pipeline != "hybrid_v2":
        raise SystemExit(
            f"production pipeline is '{trace.pipeline}', expected 'hybrid_v2'; refusing to run"
        )
    print(f"[run] warmup pipeline: {trace.pipeline} stages={list(trace.timings_ms)}")

    cases = load_jsonl(CASES_PATH)
    gold_by_case = {g["case_id"]: g for g in load_jsonl(GOLD_PATH)}
    state = _load_running_state()
    durable_results, _ = _load_resume_records(state)
    done = {row["case_id"] for row in durable_results}
    if done:
        print(f"[run] resuming {state['run_id']}: {len(done)} durable cases")
    else:
        print(f"[run] started audited run: {state['run_id']}")

    count = 0
    with (
        RAW_PATH.open("a", encoding="utf-8") as raw_fh,
        TRACES_PATH.open("a", encoding="utf-8") as trace_fh,
    ):
        for case in cases:
            if case["case_id"] in done:
                continue
            if limit is not None and count >= limit:
                break
            t0 = time.perf_counter()
            error: str | None = None
            retrieved: list[dict] = []
            trace_record: dict = {}
            try:
                result, run_trace = service.retrieve_with_trace(case["question"])
                if run_trace.pipeline != "hybrid_v2":
                    raise RuntimeError(f"pipeline_fallback:{run_trace.pipeline}")
                for rank, chunk in enumerate(result.chunks[:4], start=1):
                    retrieved.append(
                        {
                            "rank": rank,
                            "source_id": chunk.parent_doc_id,
                            "chunk_id": chunk.id,
                            "document_title": chunk.source_title or chunk.title,
                            "score": chunk.relevance_score,
                        }
                    )
                trace_record = {
                    "dense_ids": [c.id for c in run_trace.dense],
                    "lexical_ids": [c.id for c in run_trace.lexical],
                    "fused_ids": [c.id for c in run_trace.fused],
                    "reranked_ids": [c.id for c in run_trace.reranked],
                    "selected_ids": [c.id for c in run_trace.selected],
                    "timings_ms": run_trace.timings_ms,
                    "fallback_reason": run_trace.fallback_reason,
                }
            except Exception as exc:  # noqa: BLE001 - invalidate instead of filtering failures
                reason = f"{case['case_id']}: {type(exc).__name__}: {exc}"
                _mark_invalid(state, reason)
                raise SystemExit(f"formal run invalidated: {reason}") from exc
            latency_ms = (time.perf_counter() - t0) * 1000

            acceptable = set(gold_by_case[case["case_id"]]["acceptable_gold_chunk_ids"])
            hit_ranks = [item["rank"] for item in retrieved if item["chunk_id"] in acceptable]
            record = {
                "case_id": case["case_id"],
                "question": case["question"],
                "category": case["category"],
                "difficulty": case["difficulty"],
                "gold_source_ids": case["gold_source_ids"],
                "gold_chunk_ids": case["gold_chunk_ids"],
                "retrieved": retrieved,
                "top1_hit": bool(hit_ranks and hit_ranks[0] == 1),
                "top4_hit": bool(hit_ranks),
                "first_relevant_rank": hit_ranks[0] if hit_ranks else None,
                "latency_ms": round(latency_ms, 1),
                "error": error,
            }
            raw_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw_fh.flush()
            os.fsync(raw_fh.fileno())
            trace_fh.write(
                json.dumps({"case_id": case["case_id"], **trace_record}, ensure_ascii=False) + "\n"
            )
            trace_fh.flush()
            os.fsync(trace_fh.fileno())
            count += 1
            _write_checkpoint(state, case["case_id"], len(done) + count)
            if count % 50 == 0:
                print(
                    f"[run] {count} new cases done (last={case['case_id']}, {latency_ms:.0f} ms)",
                    flush=True,
                )
    completed = len(done) + count
    if completed == FINAL_TOTAL:
        state = {
            **state,
            "status": "completed",
            "updated_at_utc": utc_now(),
            "completed_cases": completed,
        }
        atomic_write_json(RUN_STATE_PATH, state)
        print(f"[run] formal pass completed: {state['run_id']} ({completed} cases)")
    else:
        print(f"[run] checkpointed {state['run_id']}: {completed}/{FINAL_TOTAL} cases")


def classify_failure(record: dict, trace: dict) -> str:
    """Deterministic failure taxonomy; rules documented in methodology.md."""
    gold = record["gold_chunk_ids"][0]
    gold_doc = (record["gold_source_ids"] or [None])[0]
    selected_ids = trace.get("selected_ids") or []
    reranked_ids = trace.get("reranked_ids") or []
    fused_ids = trace.get("fused_ids") or []
    dense_ids = trace.get("dense_ids") or []
    lexical_ids = trace.get("lexical_ids") or []
    retrieved_docs = {item.get("source_id") for item in record["retrieved"]}

    if gold in selected_ids:
        return "other"  # inconsistent bookkeeping; flag instead of mislabeling
    if gold in reranked_ids:
        if gold_doc in retrieved_docs:
            return "duplicate_evidence_crowding"
        return "reranker_demotion"
    if gold_doc in retrieved_docs:
        # The gold document surfaced a different chunk/split into Top-4.
        return "chunk_granularity"
    if gold in fused_ids:
        return "reranker_demotion"  # cut outside the reranker candidate budget
    if gold in lexical_ids and gold not in dense_ids:
        return "semantic_mismatch"
    return "other" if (gold in dense_ids or gold in lexical_ids) else "semantic_mismatch"


def cmd_summarize() -> None:
    settings = _get_settings()
    _verify_frozen_config(settings)
    if not RUN_STATE_PATH.exists():
        raise SystemExit("formal_run_state.json missing")
    state = json.loads(RUN_STATE_PATH.read_text(encoding="utf-8"))
    if state.get("status") != "completed":
        raise SystemExit(f"formal run status is {state.get('status')}; refusing to summarize")
    results = load_jsonl(RAW_PATH)
    traces = {t["case_id"]: t for t in load_jsonl(TRACES_PATH)}
    if len(results) != FINAL_TOTAL:
        print(f"WARNING: raw_results has {len(results)} cases (expected {FINAL_TOTAL})")

    def metrics(subset: list[dict]) -> dict:
        n = len(subset)
        if n == 0:
            return {}
        top1 = sum(1 for r in subset if r["top1_hit"])
        top4 = sum(1 for r in subset if r["top4_hit"])
        mrr = sum(1.0 / r["first_relevant_rank"] for r in subset if r["first_relevant_rank"]) / n
        return {
            "total": n,
            "top1_hit_count": top1,
            "top1_hit_rate": round(top1 / n * 100, 2),
            "top4_hit_count": top4,
            "top4_hit_rate": round(top4 / n * 100, 2),
            "mrr": round(mrr, 4),
            "error_count": sum(1 for r in subset if r["error"]),
        }

    latencies = sorted(r["latency_ms"] for r in results if r["error"] is None)
    overall = metrics(results)
    summary = {
        "status": "completed",
        "total_cases": len(results),
        "top1_hit_count": overall["top1_hit_count"],
        "top1_hit_rate": overall["top1_hit_rate"],
        "top4_hit_count": overall["top4_hit_count"],
        "top4_hit_rate": overall["top4_hit_rate"],
        "mrr": overall["mrr"],
        "mean_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "median_latency_ms": round(latencies[len(latencies) // 2], 1) if latencies else None,
        "p95_latency_ms": round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))], 1)
        if latencies
        else None,
        "error_count": overall["error_count"],
        "by_difficulty": {},
        "by_category": {},
    }
    for diff in ("easy", "medium", "hard"):
        summary["by_difficulty"][diff] = metrics([r for r in results if r["difficulty"] == diff])
    for cat in sorted({r["category"] for r in results}):
        summary["by_category"][cat] = metrics([r for r in results if r["category"] == cat])

    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in {"by_difficulty", "by_category"}},
            indent=2,
        )
    )

    # Failure cases (all Top-4 misses, kept; never removed)
    failures = []
    for record in results:
        if not record["top4_hit"]:
            trace = traces.get(record["case_id"], {})
            failure_type = classify_failure(record, trace)
            failures.append(
                {
                    "case_id": record["case_id"],
                    "question": record["question"],
                    "category": record["category"],
                    "difficulty": record["difficulty"],
                    "gold_chunk_ids": record["gold_chunk_ids"],
                    "failure_type": failure_type,
                    "retrieved": record["retrieved"],
                    "trace": {
                        "fused_ids": trace.get("fused_ids", []),
                        "reranked_ids": trace.get("reranked_ids", []),
                        "selected_ids": trace.get("selected_ids", []),
                    },
                }
            )
    with FAILURES_PATH.open("w", encoding="utf-8") as fh:
        for failure in failures:
            fh.write(json.dumps(failure, ensure_ascii=False) + "\n")
    print(f"[summarize] failures: {len(failures)} -> {FAILURES_PATH}")
    type_counts = Counter(f["failure_type"] for f in failures)
    diff_fail = Counter(f["difficulty"] for f in failures)
    print("failure types:", dict(type_counts))
    print("failures by difficulty:", dict(diff_fail))


def cmd_invalidate(reason: str) -> None:
    if not RUN_STATE_PATH.exists():
        raise SystemExit("no formal run state exists")
    state = json.loads(RUN_STATE_PATH.read_text(encoding="utf-8"))
    if state.get("status") != "running":
        raise SystemExit(
            f"only a running formal pass can be invalidated; status={state.get('status')}"
        )
    _mark_invalid(state, reason)
    print(f"[invalidate] {state['run_id']}: {reason}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["validate", "run", "summarize", "invalidate"])
    parser.add_argument(
        "--limit", type=int, default=None, help="run only N pending cases (smoke test)"
    )
    parser.add_argument("--reason", help="audit reason required by the invalidate stage")
    args = parser.parse_args()
    if args.stage == "validate":
        cmd_validate()
    elif args.stage == "run":
        cmd_run(args.limit)
    elif args.stage == "summarize":
        cmd_summarize()
    else:
        if not args.reason:
            parser.error("invalidate requires --reason")
        cmd_invalidate(args.reason)


if __name__ == "__main__":
    main()
