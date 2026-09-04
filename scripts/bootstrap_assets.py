"""Restore functional runtime assets without downloading a prebuilt RAG index."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
MANIFEST_PATH = REPO_ROOT / "assets" / "runtime-assets-manifest.json"


def run(command: list[str], *, environment: dict[str, str], cwd: Path = REPO_ROOT) -> None:
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def ensure_backend_dependencies() -> None:
    try:
        import pymupdf  # noqa: F401
        import sentence_transformers  # noqa: F401
    except ImportError:
        print("installing the local backend helper dependencies required for bootstrap")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(BACKEND)], check=True
        )


def restore_models(manifest: dict[str, object], cache_dir: Path) -> None:
    # Xet-backed transfers can stall behind some enterprise proxies.  The
    # ordinary Hugging Face HTTP path is more widely deployable and still
    # resolves the exact commit below.  Set this before importing the client.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        ensure_backend_dependencies()
        try:
            from huggingface_hub import snapshot_download
        except ImportError as second_exc:  # pragma: no cover - defensive install failure
            raise SystemExit("bootstrap dependencies could not be installed") from second_exc
    for role, details in manifest["models"].items():
        expected = REPO_ROOT / details["expected_path"]
        for attempt in range(1, 4):
            if expected.is_dir() and model_loads_offline(role, expected):
                print(f"{role}: fixed revision is present and loads offline")
                break
            print(
                f"{role}: downloading {details['name']} @ {details['revision']} "
                f"from Hugging Face (attempt {attempt}/3)"
            )
            snapshot_download(
                repo_id=details["name"],
                revision=details["revision"],
                cache_dir=str(cache_dir),
                max_workers=1,
            )
            if expected.is_dir() and model_loads_offline(role, expected):
                print(f"{role}: official fixed revision restored and loads offline")
                break
            if attempt == 3:
                raise SystemExit(
                    f"{role}: fixed revision download is incomplete or cannot load offline: "
                    f"{expected}"
                )
            time.sleep(attempt)


def model_loads_offline(role: str, snapshot: Path) -> bool:
    """Require the real model weights, not merely a Hugging Face snapshot directory."""
    try:
        if role == "embedding":
            from sentence_transformers import SentenceTransformer

            SentenceTransformer(str(snapshot), local_files_only=True, device="cpu")
        elif role == "reranker":
            from sentence_transformers import CrossEncoder

            CrossEncoder(str(snapshot), local_files_only=True, device="cpu")
        else:  # pragma: no cover - manifest roles are repository-controlled
            raise ValueError(f"unknown model role: {role}")
    except Exception as exc:  # noqa: BLE001 - report a failed third-party model load
        print(f"{role}: offline model validation failed: {exc}")
        return False
    return True


def smoke(environment: dict[str, str]) -> None:
    for question in ("疫苗接种有什么作用？", "什么是群体免疫？", "为什么需要完成全程接种？"):
        run(
            [sys.executable, "-m", "app.rag.cli", "query", question],
            environment=environment,
            cwd=BACKEND,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--rebuild-index", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ensure_backend_dependencies()
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(BACKEND),
            "RAG_EMBEDDING_REVISION": manifest["models"]["embedding"]["revision"],
            "RAG_RERANKER_REVISION": manifest["models"]["reranker"]["revision"],
            "GRAPH_RAG_ENABLED": "false",
        }
    )
    restore_models(manifest, BACKEND / "model_cache")
    if args.verify_only:
        run(
            [sys.executable, str(REPO_ROOT / "scripts" / "verify_assets.py")],
            environment=environment,
        )
        return
    active = BACKEND / "rag_index" / "active.json"
    if args.rebuild_index or not active.is_file():
        run(
            [sys.executable, str(REPO_ROOT / "scripts" / "rebuild_rag_index.py")],
            environment=environment,
        )
    run([sys.executable, str(REPO_ROOT / "scripts" / "verify_assets.py")], environment=environment)
    smoke(environment)
    print("bootstrap complete: GraphRAG remains optional and is disabled for this local rebuild")


if __name__ == "__main__":
    main()
