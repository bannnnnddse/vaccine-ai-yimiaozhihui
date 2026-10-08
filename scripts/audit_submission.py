"""Read-only submission inventory; no model, network, index writes or medical scoring."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def jsonl(relative_path: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / relative_path).read_text(
        encoding="utf-8-sig"
    ).splitlines() if line.strip()]


def main() -> None:
    manifest = jsonl("RAG/corpus_manifest.jsonl")
    cases = jsonl("docs/evaluation/rag_v2/evaluation_cases.jsonl")
    results = jsonl("docs/evaluation/rag_v2/raw_results.jsonl")
    retrieved = [item["chunk_id"] for row in results for item in row["retrieved"][:4]]
    tracked = set(subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT, encoding="utf-8"
    ).split("\0"))
    videos = ["frontend/public/assets/science-videos/" + filename for filename in (
        "virus-adventure-episode-1.mp4", "vaccine-defense-episode-2.mp4"
    )]
    report = {
        "corpus": {
            "manifest_entries": len(manifest),
            "evidence_levels": dict(Counter(row.get("evidence_level") for row in manifest)),
            "metadata_confidence": dict(Counter(
                row.get("metadata_confidence") for row in manifest
            )),
            "languages": dict(Counter(row.get("language") for row in manifest)),
            "publication_date_missing": sum(not row.get("publication_date") for row in manifest),
            "download_placeholders": sum(
                row.get("source_type") == "download_placeholder" for row in manifest
            ),
            "rabies_manifest_matches": sum(any(word in json.dumps(
                row, ensure_ascii=False
            ).lower() for word in ("狂犬", "暴露", "咬伤", "rabies")) for row in manifest),
            "missing_manifest_files": [row["relative_path"] for row in manifest
                                       if not (ROOT / "RAG" / row["relative_path"]).is_file()],
        },
        "visual_fact_allowlist_entries": len(json.loads((
            ROOT / "backend/app/data/verified_visual_facts.json"
        ).read_text(encoding="utf-8"))),
        "benchmark": {
            "cases": len(cases),
            "unique_acceptable_gold_chunks": len({chunk for row in cases
                                                   for chunk in row["acceptable_gold_chunk_ids"]}),
            "top4_items": len(retrieved),
            "unique_top4_chunks": len(set(retrieved)),
            "top4_hits": sum(row["top4_hit"] for row in results),
        },
        "video_assets": [{"path": path, "tracked": path in tracked,
                          "present_locally": (ROOT / path).is_file()} for path in videos],
        "tracked_local_artifacts": sorted(path for path in tracked if path and (
            path.startswith(("docs/evaluation/rag_v2/build/", "backend/runtime/",
                             "backend/rag_index/", "backend/model_cache/"))
            or (path.startswith("vaccine-ai") and path.endswith("-source.zip"))
        )),
        "scientific_review_status": json.loads((
            ROOT / "docs/evaluation/scientific_correctness/review_status.json"
        ).read_text(encoding="utf-8")),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
