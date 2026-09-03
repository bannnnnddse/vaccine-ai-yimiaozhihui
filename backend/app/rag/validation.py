from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from app.core.config import Settings
from app.graph.validation import validate_graph_artifacts
from app.rag.index_versions import version_directory
from app.rag.numpy_store import NumpyRagStore


def validate_candidate_index(
    settings: Settings,
    index_version: str,
    *,
    evaluation_report: Path | None = None,
) -> dict[str, object]:
    candidate = version_directory(settings.rag_index_dir, index_version)
    manifest_path = candidate / "manifest.json"
    catalog_path = candidate / "chunks.jsonl"
    failures: list[str] = []
    if not manifest_path.is_file() or not catalog_path.is_file():
        raise FileNotFoundError(f"candidate index is incomplete: {index_version}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("index_version") != index_version:
        failures.append("index manifest version mismatch")
    if manifest.get("status") != "candidate":
        failures.append("index is not marked as a candidate")
    if sha256(catalog_path.read_bytes()).hexdigest() != manifest.get("chunk_catalog_hash"):
        failures.append("chunk catalog hash mismatch")
    info = NumpyRagStore(candidate, settings.rag_collection_name, embedder=None).inspect_index()
    if info["count"] != manifest.get("chunk_count"):
        failures.append("dense store count does not match index manifest")
    metadata = info["metadata"]
    if metadata.get("index_version") != index_version:
        failures.append("dense store index version mismatch")
    if metadata.get("corpus_manifest_hash") != manifest.get("corpus_manifest_hash"):
        failures.append("dense store corpus manifest hash mismatch")
    if manifest.get("document_count") != manifest.get("accepted_document_count"):
        failures.append("not every accepted document produced an indexed chunk")
    graph_validation: dict[str, object] | None = None
    if settings.graph_rag_enabled or manifest.get("graph") is not None:
        try:
            graph_validation = validate_graph_artifacts(
                candidate / "graph",
                index_version=index_version,
                chunk_catalog_path=catalog_path,
            )
            graph_manifest = json.loads(
                (candidate / "graph" / "manifest.json").read_text(encoding="utf-8")
            )
            if graph_manifest.get("schema_version") != settings.graph_schema_version:
                failures.append("configured graph schema version mismatch")
            if (
                graph_manifest.get("extraction_rules_version")
                != settings.graph_extraction_rules_version
            ):
                failures.append("configured graph extraction rules version mismatch")
            graph_manifest_hash = sha256(
                (candidate / "graph" / "manifest.json").read_bytes()
            ).hexdigest()
            if (manifest.get("graph") or {}).get("manifest_sha256") != graph_manifest_hash:
                failures.append("graph manifest hash mismatch")
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            failures.append(str(exc))

    evaluation: dict[str, object] | None = None
    if evaluation_report is not None:
        evaluation = json.loads(evaluation_report.read_text(encoding="utf-8"))
        if evaluation.get("index_version") != index_version:
            failures.append("evaluation report targets a different index version")
        if evaluation.get("gate_passed") is not True:
            failures.append("evaluation gate did not pass")
    report = {
        "index_version": index_version,
        "valid": not failures,
        "failures": failures,
        "document_count": manifest.get("document_count"),
        "chunk_count": manifest.get("chunk_count"),
        "evaluation_gate_passed": evaluation.get("gate_passed") if evaluation else None,
        "graph": graph_validation,
    }
    if failures:
        raise ValueError("candidate validation failed: " + "; ".join(failures))
    return report
