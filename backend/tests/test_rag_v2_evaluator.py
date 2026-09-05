from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_rag_v2.py"


def _load_evaluator():
    spec = importlib.util.spec_from_file_location("evaluate_rag_v2_for_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configure_run_paths(module, tmp_path: Path) -> None:
    module.RAW_PATH = tmp_path / "raw_results.jsonl"
    module.TRACES_PATH = tmp_path / "raw_traces.jsonl"
    module.RUN_STATE_PATH = tmp_path / "formal_run_state.json"
    module.CHECKPOINT_PATH = tmp_path / "formal_checkpoint.json"
    module.INVALID_RUNS_PATH = tmp_path / "invalid_runs.jsonl"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_resume_accepts_aligned_durable_artifacts(tmp_path: Path) -> None:
    evaluator = _load_evaluator()
    _configure_run_paths(evaluator, tmp_path)
    state = {"run_id": "formal-test", "freeze_manifest_sha256": "frozen"}
    _write_jsonl(evaluator.RAW_PATH, [{"case_id": "RAGV2-0001"}])
    _write_jsonl(evaluator.TRACES_PATH, [{"case_id": "RAGV2-0001"}])
    evaluator.atomic_write_json(
        evaluator.CHECKPOINT_PATH,
        {"run_id": "formal-test", "completed_cases": 1},
    )

    results, traces = evaluator._load_resume_records(state)

    assert [row["case_id"] for row in results] == ["RAGV2-0001"]
    assert [row["case_id"] for row in traces] == ["RAGV2-0001"]
    assert not evaluator.INVALID_RUNS_PATH.exists()


def test_resume_mismatch_is_recorded_as_invalid(tmp_path: Path) -> None:
    evaluator = _load_evaluator()
    _configure_run_paths(evaluator, tmp_path)
    state = {
        "run_id": "formal-test",
        "status": "running",
        "freeze_manifest_sha256": "frozen",
    }
    _write_jsonl(evaluator.RAW_PATH, [{"case_id": "RAGV2-0001"}])
    _write_jsonl(evaluator.TRACES_PATH, [{"case_id": "RAGV2-0002"}])

    with pytest.raises(SystemExit, match="marked invalid"):
        evaluator._load_resume_records(state)

    invalid = evaluator.load_jsonl(evaluator.INVALID_RUNS_PATH)
    assert invalid[0]["run_id"] == "formal-test"
    assert "misaligned" in invalid[0]["reason"]
    run_state = json.loads(evaluator.RUN_STATE_PATH.read_text(encoding="utf-8"))
    assert run_state["status"] == "invalid"
