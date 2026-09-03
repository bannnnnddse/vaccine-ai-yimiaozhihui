#!/usr/bin/env python3
"""Scientific-correctness evaluation runner for the production QA pipeline.

Two modes:
  --run        Run all 20 cases through the real POST /api/v1/chat pipeline
               (FastAPI TestClient, full lifespan: RagService/QwenService/
               EvidenceAssessment/PubMed) and freeze raw outputs to
               docs/evaluation/scientific_correctness/raw_outputs.jsonl.
  --summarize  Read human_review.csv; only when all 20 cases are reviewed,
               produce summary.json (status=completed) and update the results
               section of report.md. Otherwise summary stays pending_human_review.

This script never invents metrics: summary numbers come exclusively from
human_review.csv. It also never rewrites answers or resamples on content.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
SCI_DIR = REPO_ROOT / "docs" / "evaluation" / "scientific_correctness"
CASES_PATH = SCI_DIR / "evaluation_cases.jsonl"
RAW_PATH = SCI_DIR / "raw_outputs.jsonl"
REVIEW_PATH = SCI_DIR / "human_review.csv"
SUMMARY_PATH = SCI_DIR / "summary.json"
REPORT_PATH = SCI_DIR / "report.md"

REVIEW_FIELDS = [
    "case_id", "category", "risk_level", "question",
    "scientific_correct", "citation_supported", "critical_error",
    "safety_boundary", "reviewer", "notes",
]
METRIC_FIELDS = [
    "scientific_correct",
    "citation_supported",
    "critical_error",
    "safety_boundary",
]
SUMMARY_KEY = {
    "scientific_correct": "scientific_correct",
    "citation_supported": "citation_supported",
    "critical_error": "critical_error",
    "safety_boundary": "safety_boundary_pass",
}
METRIC_KEYS = [
    "scientific_correct",
    "citation_supported",
    "critical_error",
    "safety_boundary",
]


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT), text=True, encoding="utf-8",
        ).strip()
    except Exception as exc:  # noqa: BLE001 - evaluation helper, must not crash
        print(f"warning: could not read commit: {exc}", file=sys.stderr)
        return "not available"


def _load_cases() -> list[dict]:
    cases = []
    with CASES_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def run() -> int:
    sys.path.insert(0, str(BACKEND_ROOT))
    try:
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415
    except Exception as exc:
        print(f"ERROR: cannot import backend app: {exc}", file=sys.stderr)
        print("Run this from an environment where backend dependencies are installed.", file=sys.stderr)
        return 2

    cases = _load_cases()
    commit = _git_commit()
    print(f"Cases: {len(cases)}  commit: {commit[:12]}")

    with TestClient(create_app()) as client:
        records = []
        for case in cases:
            started = time.perf_counter()
            error: str | None = None
            payload: dict = {}
            try:
                resp = client.post(
                    "/api/v1/chat",
                    json={"question": case["question"]},
                    timeout=300,
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                if resp.status_code == 200:
                    body = resp.json()
                    sources = body.get("sources", [])
                    payload = {
                        "answer": body.get("answer", ""),
                        "model": body.get("model", ""),
                        "is_vaccine_related": body.get("is_vaccine_related", False),
                        "citations": [
                            {
                                "file_name": s.get("file_name"),
                                "page": s.get("page"),
                                "source_type": s.get("source_type"),
                                "title": s.get("title") or s.get("source_title"),
                            }
                            for s in sources
                        ],
                        "retrieved_evidence": [
                            {"file_name": s.get("file_name"), "content": s.get("content", "")}
                            for s in sources
                        ],
                        "knowledge_gap": len(sources) == 0,
                        "pubmed_used": any(
                            (s.get("source_type") or "") == "pubmed" for s in sources
                        ),
                        "session_id": body.get("session_id", ""),
                        "error": None,
                    }
                else:
                    payload = {
                        "answer": "", "model": "", "is_vaccine_related": False,
                        "citations": [], "retrieved_evidence": [],
                        "knowledge_gap": False, "pubmed_used": False,
                        "session_id": "",
                        "error": f"HTTP {resp.status_code}: {resp.text[:500]}",
                    }
            except Exception as exc:  # noqa: BLE001 - keep the record, record the error
                latency_ms = int((time.perf_counter() - started) * 1000)
                payload = {
                    "answer": "", "model": "", "is_vaccine_related": False,
                    "citations": [], "retrieved_evidence": [],
                    "knowledge_gap": False, "pubmed_used": False,
                    "session_id": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }

            record = {
                "case_id": case["case_id"],
                "question": case["question"],
                **payload,
                "latency_ms": latency_ms,
                "commit": commit,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            records.append(record)
            print(f"{case['case_id']}: {'ok' if not record['error'] else 'ERROR'} "
                  f"({latency_ms} ms, sources={len(record['citations'])})")

    with RAW_PATH.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} raw records -> {RAW_PATH}")
    return 0


def _review_rows() -> list[dict]:
    with REVIEW_PATH.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def summarize() -> int:
    rows = _review_rows()
    cases = _load_cases()
    total = len(cases)

    missing = [c["case_id"] for c in cases
               if not any(r["case_id"] == c["case_id"] for r in rows)]
    if missing:
        print(f"ERROR: human_review.csv is missing cases: {missing}", file=sys.stderr)
        return 2

    def filled(row: dict, field: str) -> bool:
        return row.get(field, "").strip() != ""

    reviewed = 0
    for row in rows:
        if all(filled(row, f) for f in METRIC_FIELDS):
            reviewed += 1

    summary = {
        "evaluation_name": "High-risk Vaccine QA Scientific Correctness Audit",
        "total_cases": total,
        "reviewed_cases": reviewed,
        "status": "completed" if reviewed == total else "pending_human_review",
        "scientific_correct_count": None,
        "scientific_correct_rate": None,
        "citation_supported_count": None,
        "citation_supported_rate": None,
        "critical_error_count": None,
        "critical_error_rate": None,
        "safety_boundary_pass_count": None,
        "safety_boundary_pass_rate": None,
    }

    if summary["status"] == "completed":
        counts = {f: sum(1 for r in rows if r[f].strip() == "1") for f in METRIC_FIELDS}
        for field, count in counts.items():
            key = SUMMARY_KEY[field]
            summary[f"{key}_count"] = count
            summary[f"{key}_rate"] = round(count / total * 100, 2)

    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"summary -> {SUMMARY_PATH}  status={summary['status']} reviewed={reviewed}/{total}")

    if summary["status"] == "completed":
        _update_report(summary)
    return 0


def _update_report(s: dict) -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")
    start = text.find("## 5. 结果")
    end = text.find("## 6. 指标边界")
    if start == -1 or end == -1:
        print("warning: report.md section markers not found; report not updated", file=sys.stderr)
        return
    result_block = (
        "## 5. 结果\n\n"
        f"- 核心科学结论正确：{s['scientific_correct_count']} / 20"
        f"（{s['scientific_correct_rate']:.2f}%）\n"
        f"- 关键结论具有证据支持：{s['citation_supported_count']} / 20"
        f"（{s['citation_supported_rate']:.2f}%）\n"
        f"- 严重医学错误：{s['critical_error_count']} / 20"
        f"（{s['critical_error_rate']:.2f}%）\n"
        f"- 安全边界通过：{s['safety_boundary_pass_count']} / 20"
        f"（{s['safety_boundary_pass_rate']:.2f}%）\n\n"
        "以上数字全部来自 `human_review.csv` 的人工判定，无模型自评成分。\n\n"
    )
    REPORT_PATH.write_text(text[:start] + result_block + text[end:], encoding="utf-8")
    print(f"updated results in {REPORT_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="run 20 cases via production pipeline")
    parser.add_argument("--summarize", action="store_true", help="build summary.json from human_review.csv")
    args = parser.parse_args()
    if not args.run and not args.summarize:
        parser.print_help()
        return 1
    if args.run:
        return run()
    return summarize()


if __name__ == "__main__":
    sys.exit(main())
