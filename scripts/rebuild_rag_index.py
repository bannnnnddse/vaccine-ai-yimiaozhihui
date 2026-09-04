"""Rebuild and activate a local Hybrid RAG V2 index from the tracked corpus.

This command never creates a GraphRAG snapshot and never contacts a generative
model.  It is intentionally the rebuild fallback used by bootstrap_assets.py.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.rag.builder import build_candidate_index  # noqa: E402
from app.rag.index_versions import activate_index  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-artifacts", action="store_true")
    args = parser.parse_args()
    environment = os.environ.copy()
    environment["GRAPH_RAG_ENABLED"] = "false"
    command = [sys.executable, str(REPO_ROOT / "scripts" / "prepare_rag_artifacts.py")]
    if args.force_artifacts:
        command.append("--force")
    subprocess.run(command, cwd=REPO_ROOT, env=environment, check=True)
    os.environ["GRAPH_RAG_ENABLED"] = "false"
    # .env paths are intentionally relative to backend/, as are the Docker
    # defaults.  Run the existing V2 builder from that same directory.
    os.chdir(BACKEND)
    get_settings.cache_clear()
    settings = get_settings()
    try:
        import torch

        torch.set_num_threads(settings.rag_torch_num_threads)
        torch.set_num_interop_threads(settings.rag_torch_interop_threads)
    except (ImportError, RuntimeError):
        # The builder remains usable in minimal environments without torch
        # thread controls; SentenceTransformers will report model errors later.
        pass
    manifest = build_candidate_index(settings, local_files_only=True)
    pointer = activate_index(settings.rag_index_dir, str(manifest["index_version"]))
    print(f"activated local Hybrid RAG index: {pointer['index_version']}")


if __name__ == "__main__":
    main()
