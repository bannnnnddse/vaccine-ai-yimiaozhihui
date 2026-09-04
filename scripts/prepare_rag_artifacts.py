"""Create portable, loader-compatible PDF text artifacts from the tracked corpus.

These artifacts are generated locally under backend/runtime and are deliberately
not a distributed runtime asset.  They supply the existing V2 builder with page
blocks when the production-only Docling exports are absent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

import pymupdf  # noqa: E402

from app.rag.corpus import load_corpus_manifest  # noqa: E402
from app.rag.text import clean_text  # noqa: E402


def accepted_pdf_documents(manifest: Path):
    return [
        document
        for document in load_corpus_manifest(manifest)
        if (
            not document.duplicate_of
            and document.parse_status in {"parsed", "partial", "ocr_parsed"}
            and document.source_type != "download_placeholder"
            and document.authority_level > 0
            and document.filename.lower().endswith(".pdf")
        )
    ]


def build_artifact(source: Path, target: Path) -> None:
    texts: list[dict[str, object]] = []
    children: list[dict[str, str]] = []
    with pymupdf.open(source) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = clean_text(page.get_text("text"))
            if not text:
                continue
            index = len(texts)
            texts.append(
                {
                    "text": text,
                    "label": "text",
                    "prov": [{"page_no": page_number}],
                }
            )
            children.append({"$ref": f"#/texts/{index}"})
    payload = {"texts": texts, "tables": [], "groups": [], "body": {"children": children}}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="replace existing local artifacts")
    args = parser.parse_args()
    source_dir = REPO_ROOT / "RAG"
    manifest = source_dir / "corpus_manifest.jsonl"
    artifact_dir = BACKEND / "runtime" / "docling_v2"
    if not manifest.is_file():
        raise SystemExit(f"missing tracked corpus manifest: {manifest}")
    written = skipped = 0
    for document in accepted_pdf_documents(manifest):
        source = source_dir / document.relative_path
        target = artifact_dir / f"{document.doc_id}.json"
        if target.is_file() and not args.force:
            skipped += 1
            continue
        if not source.is_file():
            raise SystemExit(f"missing corpus PDF: {source}")
        build_artifact(source, target)
        written += 1
    print(f"portable PDF artifacts ready: written={written} reused={skipped} dir={artifact_dir}")


if __name__ == "__main__":
    main()
