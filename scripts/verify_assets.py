"""Verify the locally restored functional-reproducibility assets."""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "assets" / "runtime-assets-manifest.json"


def model_loads_offline(role: str, snapshot: Path) -> str | None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        if role == "embedding":
            from sentence_transformers import SentenceTransformer

            SentenceTransformer(str(snapshot), local_files_only=True, device="cpu")
        elif role == "reranker":
            from sentence_transformers import CrossEncoder

            CrossEncoder(str(snapshot), local_files_only=True, device="cpu")
        else:  # pragma: no cover - manifest roles are repository-controlled
            return f"unknown model role {role}"
    except Exception as exc:  # noqa: BLE001 - report a failed third-party model load
        return str(exc)
    return None


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures: list[str] = []
    for role, model in data["models"].items():
        snapshot = REPO_ROOT / model["expected_path"]
        if not snapshot.is_dir():
            failures.append(f"missing {role} model revision {model['revision']}")
        else:
            load_error = model_loads_offline(role, snapshot)
            if load_error:
                failures.append(f"{role} fixed revision cannot load offline: {load_error}")
    active = REPO_ROOT / "backend" / "rag_index" / "active.json"
    if not active.is_file():
        failures.append("missing active RAG index pointer")
    else:
        index_version = json.loads(active.read_text(encoding="utf-8")).get("index_version")
        index_dir = REPO_ROOT / "backend" / "rag_index" / "versions" / str(index_version)
        for name in (
            "chunks.jsonl",
            "dense_records.jsonl",
            "dense_store.json",
            "vectors.npy",
            "manifest.json",
        ):
            if not (index_dir / name).is_file():
                failures.append(f"active RAG index missing {name}")
    if failures:
        raise SystemExit("asset verification failed:\n- " + "\n- ".join(failures))
    print("asset verification passed: fixed upstream models and local Hybrid RAG are ready")


if __name__ == "__main__":
    main()
