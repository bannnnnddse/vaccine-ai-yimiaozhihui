"""Evaluate a candidate with local RAG only; never activate, download or call an LLM."""

from __future__ import annotations

import argparse
import json
import os
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.chdir(BACKEND)

    import torch

    from app.core.config import get_settings
    from app.rag.service import RagService
    from app.rag.validation import validate_candidate_index

    settings = get_settings().model_copy(update={"graph_rag_enabled": False})
    torch.set_num_threads(settings.rag_torch_num_threads)
    torch.set_num_interop_threads(settings.rag_torch_interop_threads)
    case_path = ROOT / "docs/evaluation/rabies_2023/retrieval_cases.jsonl"
    cases = [json.loads(line) for line in case_path.read_text(encoding="utf-8").splitlines()]
    service = RagService.for_index_version(settings, args.index_version)
    results = []
    for case in cases:
        result, trace = service.retrieve_with_trace(case["question"])
        guideline = [chunk for chunk in result.chunks if chunk.relative_path == (
            "国家政策与免疫规划/狂犬病暴露预防处置工作规范（2023年版）.md"
        )]
        if case["kind"] == "positive":
            passed = any(
                case["expected_article"] in (chunk.section or "")
                and case["expected_text"] in chunk.text
                for chunk in guideline
            )
        else:
            passed = not guideline
        passed = passed and trace.pipeline == "hybrid_v2" and trace.fallback_reason is None
        results.append({
            **case,
            "passed": passed,
            "pipeline": trace.pipeline,
            "fallback_reason": trace.fallback_reason,
            "timings_ms": trace.timings_ms,
            "retrieved": [{
                "chunk_id": chunk.id, "relative_path": chunk.relative_path,
                "section": chunk.section, "source_url": chunk.source_url,
            } for chunk in result.chunks],
        })
        print(f"{case['case_id']}: {'PASS' if passed else 'FAIL'}", flush=True)
    report = {
        "index_version": args.index_version,
        "scope": "Local candidate retrieval smoke; not medical-answer accuracy or a full benchmark",
        "case_set_sha256": sha256(case_path.read_bytes()).hexdigest(),
        "corpus_manifest_sha256": sha256(
            settings.rag_corpus_manifest_path.read_bytes()
        ).hexdigest(),
        "total_cases": len(cases),
        "passed_cases": sum(row["passed"] for row in results),
        "gate_passed": all(row["passed"] for row in results),
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validate_candidate_index(settings, args.index_version)
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
