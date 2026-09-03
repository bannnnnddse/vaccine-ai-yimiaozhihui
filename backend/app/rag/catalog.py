from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from app.rag.models import TextChunk


def write_chunk_catalog(path: Path, chunks: list[TextChunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for chunk in chunks:
                stream.write(json.dumps(asdict(chunk), ensure_ascii=False, sort_keys=True))
                stream.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_chunk_catalog(path: Path) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            values = json.loads(line)
            values["section_path"] = tuple(values.get("section_path") or ())
            chunks.append(TextChunk(**values))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid chunk catalog line {line_number}") from exc
    return chunks
