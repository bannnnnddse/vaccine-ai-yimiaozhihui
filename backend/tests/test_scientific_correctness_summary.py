"""Disputed human reviews must not become accepted metrics during summarization."""

import importlib.util
import json
from pathlib import Path


def _runner(monkeypatch, tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/evaluate_scientific_correctness.py"
    spec = importlib.util.spec_from_file_location("scientific_summary_runner", script)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "_load_cases", lambda: [{"case_id": "SCI-013"}])
    monkeypatch.setattr(runner, "_review_rows", lambda: [{
        "case_id": "SCI-013", "scientific_correct": "1", "citation_supported": "1",
        "critical_error": "0", "safety_boundary": "1",
    }])
    for name in ("REVIEW_STATUS_PATH", "SUMMARY_PATH", "REPORT_PATH"):
        monkeypatch.setattr(runner, name, tmp_path / name)
    runner.REPORT_PATH.write_text("Original audit with unresolved evidence", encoding="utf-8")
    return runner


def test_summary_withholds_disputed_metrics_and_preserves_report(monkeypatch, tmp_path):
    runner = _runner(monkeypatch, tmp_path)
    runner.REVIEW_STATUS_PATH.write_text(json.dumps({
        "status": "pending_human_recheck", "pending_case_ids": ["SCI-013"],
    }), encoding="utf-8")

    assert runner.summarize() == 0
    summary = json.loads(runner.SUMMARY_PATH.read_text(encoding="utf-8"))
    assert summary["status"] == "pending_human_recheck"
    assert summary["scientific_correct_rate"] is None
    assert summary["citation_supported_rate"] is None
    assert summary["historical_review_counts"]["citation_supported"] == 1
    assert runner.REPORT_PATH.read_text(encoding="utf-8") == (
        "Original audit with unresolved evidence"
    )


def test_conflicting_completed_status_cannot_clear_dispute(monkeypatch, tmp_path):
    runner = _runner(monkeypatch, tmp_path)
    runner.REVIEW_STATUS_PATH.write_text(json.dumps({
        "status": "completed", "pending_case_ids": ["SCI-013"],
    }), encoding="utf-8")

    assert runner.summarize() == 2
    assert not runner.SUMMARY_PATH.exists()
