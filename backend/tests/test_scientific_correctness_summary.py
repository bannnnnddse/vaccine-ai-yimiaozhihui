"""Disputed human reviews must not become accepted metrics during summarization."""

import hashlib
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


def _completed_rerun(runner):
    base = runner.REVIEW_STATUS_PATH.parent
    response = {"answer": "offline response fixture", "sources": []}
    digest = hashlib.sha256(json.dumps(
        response, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    scores = {field: 0 for field in runner.METRIC_FIELDS}
    (base / "run.json").write_text(json.dumps({
        "case_id": "SCI-013", "response": response, "human_review_status": "completed",
        "timestamp": "fixture-time", "application_commit": "fixture-commit",
        "reviewed_response_sha256": digest,
    }), encoding="utf-8")
    (base / "review.json").write_text(json.dumps({
        "case_id": "SCI-013", "human_review_status": "completed", "reviewer": "Tutor",
        "reviewed_record": "run.json", "reviewed_run_timestamp": "fixture-time",
        "reviewed_application_commit": "fixture-commit", "response_sha256": digest,
        "scores": scores, "confirmation_basis": {"type": "explicit human confirmation"},
    }), encoding="utf-8")
    runner.REVIEW_STATUS_PATH.write_text(json.dumps({
        "status": "pending_human_recheck", "pending_case_ids": ["SCI-013"],
        "latest_reruns": {"SCI-013": {
            "human_review_status": "completed", "record": "run.json",
            "human_review_record": "review.json", "response_sha256": digest, "scores": scores,
        }},
    }), encoding="utf-8")


def test_new_response_review_is_separate_from_frozen_metrics(monkeypatch, tmp_path):
    runner = _runner(monkeypatch, tmp_path)
    _completed_rerun(runner)
    assert runner.summarize() == 0
    summary = json.loads(runner.SUMMARY_PATH.read_text(encoding="utf-8"))
    assert summary["historical_review_counts"]["scientific_correct"] == 1
    review = summary["rerun_reviews"][0]
    assert review["scores"]["scientific_correct"] == 0
    assert review["included_in_frozen_metrics"] is False
    assert summary["scientific_correct_rate"] is None


def test_changed_returned_response_invalidates_review_binding(monkeypatch, tmp_path):
    runner = _runner(monkeypatch, tmp_path)
    _completed_rerun(runner)
    run_path = tmp_path / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["response"]["answer"] = "changed answer"
    run_path.write_text(json.dumps(run), encoding="utf-8")
    assert runner.summarize() == 2
    assert not runner.SUMMARY_PATH.exists()


def test_explicitly_selected_review_replaces_original_score_once(monkeypatch, tmp_path):
    runner = _runner(monkeypatch, tmp_path)
    _completed_rerun(runner)
    status = json.loads(runner.REVIEW_STATUS_PATH.read_text(encoding="utf-8"))
    status.update(status="completed", pending_case_ids=[], status_scope="current_20_case_audit")
    status["latest_reruns"]["SCI-013"]["include_in_current_metrics"] = True
    runner.REVIEW_STATUS_PATH.write_text(json.dumps(status), encoding="utf-8")
    assert runner.summarize() == 0
    summary = json.loads(runner.SUMMARY_PATH.read_text(encoding="utf-8"))
    assert summary["total_cases"] == summary["reviewed_cases"] == 1
    assert summary["scientific_correct_count"] == 0
    assert summary["status"] == "completed"
    assert summary["rerun_reviews"][0]["included_in_current_metrics"] is True
