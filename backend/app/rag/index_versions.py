from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def new_index_version(corpus_manifest_hash: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"rag-v2-{timestamp}-{corpus_manifest_hash[:8]}"


def version_directory(index_root: Path, index_version: str) -> Path:
    if not index_version or any(value in index_version for value in ("/", "\\", "..")):
        raise ValueError("unsafe index version")
    return index_root / "versions" / index_version


def resolve_active_index(index_root: Path) -> tuple[Path, str]:
    pointer_path = index_root / "active.json"
    if not pointer_path.is_file():
        return index_root, "legacy"
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        index_version = str(pointer["index_version"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("active RAG index pointer is invalid") from exc
    candidate = version_directory(index_root, index_version).resolve()
    versions_root = (index_root / "versions").resolve()
    if versions_root not in candidate.parents or not candidate.is_dir():
        raise RuntimeError("active RAG index version is unavailable")
    return candidate, index_version


def read_active_pointer(index_root: Path) -> dict[str, str]:
    pointer_path = index_root / "active.json"
    if not pointer_path.is_file():
        return {"index_version": "legacy"}
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if not isinstance(pointer.get("index_version"), str):
            raise ValueError("missing index version")
        if pointer.get("graph_version") is not None and not isinstance(
            pointer["graph_version"], str
        ):
            raise ValueError("invalid graph version")
        return pointer
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("active RAG index pointer is invalid") from exc


def activate_index(
    index_root: Path,
    index_version: str,
    graph_version: str | None = None,
) -> dict[str, str]:
    candidate = version_directory(index_root, index_version)
    manifest = candidate / "manifest.json"
    if not candidate.is_dir() or not manifest.is_file():
        raise FileNotFoundError(f"candidate index is incomplete: {index_version}")
    pointer = {
        "index_version": index_version,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    if graph_version is not None:
        pointer["graph_version"] = graph_version
    index_root.mkdir(parents=True, exist_ok=True)
    path = index_root / "active.json"
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(
            json.dumps(pointer, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return pointer


def restore_active_index(
    index_root: Path,
    index_version: str,
    graph_version: str | None = None,
) -> None:
    if index_version == "legacy":
        (index_root / "active.json").unlink(missing_ok=True)
        return
    activate_index(index_root, index_version, graph_version)
