"""Cross-process Chroma persistence diagnostic.

This intentionally uses synthetic vectors and no project models.  A successful
run proves that one Python environment can build an HNSW collection, terminate,
and reopen/query the complete collection from fresh processes repeatedly.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import chromadb
import numpy as np

COLLECTION_NAME = "persistence_probe"
EXPECTED_NEAREST_ID = "item-00000"


def _vectors(count: int, dimensions: int) -> np.ndarray:
    generator = np.random.default_rng(20260816)
    values = generator.normal(size=(count, dimensions)).astype(np.float32)
    values /= np.linalg.norm(values, axis=1, keepdims=True)
    return values


def _configuration(profile: str) -> dict:
    hnsw: dict[str, int | str] = {"space": "cosine"}
    if profile in {"sync100", "explicit100"}:
        hnsw["sync_threshold"] = 100
    if profile == "explicit100":
        hnsw["batch_size"] = 100
    return {"hnsw": hnsw}


def _payload(start: int, stop: int, payload: str):
    if payload == "embeddings":
        return {}
    documents = ["疫苗接种与免疫效果。" * 50 for _ in range(start, stop)]
    if payload == "documents":
        return {"documents": documents}
    metadatas = [
        {
            "file_name": f"指南-{index % 131}.pdf",
            "relative_path": f"专题/指南-{index % 131}.pdf",
            "page": index % 200 + 1,
            "chunk_index": index,
            "source_hash": "a" * 64,
            "source_type": "pdf",
            "corpus_source_type": "academic_paper",
            "source_title": "疫苗研究指南",
            "source_url": "",
            "section": "接种建议",
            "parent_doc_id": "b" * 24,
            "section_path": '["第三章", "接种建议"]',
            "content_hash": "c" * 64,
            "title": "疫苗研究指南",
            "authority_level": 2,
            "evidence_level": "cohort",
            "publication_date": "2025-01-01",
            "publication_year": 2025,
            "effective_date": "",
            "version": "unknown",
            "is_superseded": False,
        }
        for index in range(start, stop)
    ]
    result = {"metadatas": metadatas}
    if payload == "full":
        result["documents"] = documents
    return result


def build(
    index_dir: Path,
    count: int,
    dimensions: int,
    profile: str,
    payload: str,
    add_batch_size: int,
) -> None:
    vectors = _vectors(count, dimensions)
    client = chromadb.PersistentClient(path=str(index_dir))
    collection = client.get_or_create_collection(
        COLLECTION_NAME,
        configuration=_configuration(profile),
    )
    for start in range(0, count, add_batch_size):
        stop = min(start + add_batch_size, count)
        collection.add(
            ids=[f"item-{index:05d}" for index in range(start, stop)],
            embeddings=vectors[start:stop].tolist(),
            **_payload(start, stop, payload),
        )
    result = collection.query(query_embeddings=[vectors[0].tolist()], n_results=1)
    if collection.count() != count or result["ids"][0][0] != EXPECTED_NEAREST_ID:
        raise RuntimeError("build-process count/query verification failed")
    client.close()


def reopen(index_dir: Path, count: int, dimensions: int) -> None:
    vectors = _vectors(count, dimensions)
    client = chromadb.PersistentClient(path=str(index_dir))
    collection = client.get_collection(COLLECTION_NAME)
    actual_count = collection.count()
    result = collection.query(query_embeddings=[vectors[0].tolist()], n_results=1)
    actual_id = result["ids"][0][0]
    client.close()
    if actual_count != count:
        raise RuntimeError(f"expected {count} vectors after reopen, got {actual_count}")
    if actual_id != EXPECTED_NEAREST_ID:
        raise RuntimeError(
            f"expected nearest id {EXPECTED_NEAREST_ID!r}, got {actual_id!r}"
        )


def run(
    index_dir: Path,
    count: int,
    dimensions: int,
    reopens: int,
    profile: str,
    payload: str,
    add_batch_size: int,
) -> None:
    if index_dir.exists():
        shutil.rmtree(index_dir)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--index-dir",
        str(index_dir),
        "--count",
        str(count),
        "--dimensions",
        str(dimensions),
        "--hnsw-profile",
        profile,
        "--payload",
        payload,
        "--add-batch-size",
        str(add_batch_size),
    ]
    subprocess.run([*command, "--phase", "build"], check=True)
    for _ in range(reopens):
        subprocess.run([*command, "--phase", "reopen"], check=True)
    print(json.dumps({
        "status": "passed",
        "chromadb": chromadb.__version__,
        "python": sys.version.split()[0],
        "count": count,
        "dimensions": dimensions,
        "reopens": reopens,
        "hnsw_profile": profile,
        "payload": payload,
        "add_batch_size": add_batch_size,
        "index_dir": str(index_dir.resolve()),
    }))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1_200)
    parser.add_argument("--dimensions", type=int, default=384)
    parser.add_argument("--reopens", type=int, default=3)
    parser.add_argument(
        "--hnsw-profile",
        choices=("default", "sync100", "explicit100"),
        default="explicit100",
    )
    parser.add_argument(
        "--payload",
        choices=("embeddings", "documents", "metadata", "full"),
        default="embeddings",
    )
    parser.add_argument("--add-batch-size", type=int, default=100)
    parser.add_argument("--phase", choices=("run", "build", "reopen"), default="run")
    args = parser.parse_args()
    if args.phase == "build":
        build(
            args.index_dir,
            args.count,
            args.dimensions,
            args.hnsw_profile,
            args.payload,
            args.add_batch_size,
        )
    elif args.phase == "reopen":
        reopen(args.index_dir, args.count, args.dimensions)
    else:
        run(
            args.index_dir,
            args.count,
            args.dimensions,
            args.reopens,
            args.hnsw_profile,
            args.payload,
            args.add_batch_size,
        )


if __name__ == "__main__":
    main()
