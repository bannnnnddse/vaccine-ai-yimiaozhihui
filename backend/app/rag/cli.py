import argparse
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.graph.builder import build_graph_for_index
from app.graph.validation import validate_graph_artifacts
from app.rag.builder import build_candidate_index, build_index
from app.rag.corpus import write_corpus_manifest
from app.rag.index_versions import activate_index, resolve_active_index
from app.rag.numpy_store import NumpyRagStore, is_numpy_index
from app.rag.service import RagService
from app.rag.store import ChromaRagStore, RagStoreError
from app.rag.validation import validate_candidate_index


def _build() -> None:
    settings = get_settings()
    manifest = build_index(settings)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def _build_v2() -> None:
    settings = get_settings()
    manifest = build_candidate_index(settings, local_files_only=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def _graph_build(index_version: str) -> None:
    settings = get_settings()
    index_dir = settings.rag_index_dir / "versions" / index_version
    manifest = build_graph_for_index(index_dir, index_version=index_version)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def _graph_inspect(index_version: str | None) -> None:
    settings = get_settings()
    if index_version is None:
        index_dir, index_version = resolve_active_index(settings.rag_index_dir)
    else:
        index_dir = settings.rag_index_dir / "versions" / index_version
    report = validate_graph_artifacts(
        index_dir / "graph",
        index_version=index_version,
        chunk_catalog_path=index_dir / "chunks.jsonl",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _inspect() -> None:
    settings = get_settings()
    active_path, index_version = resolve_active_index(settings.rag_index_dir)
    store_type = NumpyRagStore if is_numpy_index(active_path) else ChromaRagStore
    store = store_type(active_path, settings.rag_collection_name, embedder=None)
    try:
        info = store.inspect_index()
    except RagStoreError as exc:
        print(f"索引不可用：{exc}")
        sys.exit(1)
    print(
        f"index_version={index_version} collection={settings.rag_collection_name} "
        f"count={info['count']}"
    )
    print(f"metadata={json.dumps(info['metadata'], ensure_ascii=False)}")
    manifest_path = active_path / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if index_version == "legacy":
            print(
                f"manifest: {manifest['created_at']} pdf={manifest['pdf_files_seen']} "
                f"unique={manifest['unique_pdf_files']} "
                f"markdown={manifest.get('unique_markdown_files', 0)} "
                f"chunks={manifest['chunks_indexed']}"
            )
        else:
            print(
                f"manifest: {manifest['build_timestamp']} "
                f"documents={manifest['document_count']} chunks={manifest['chunk_count']}"
            )
    else:
        print("manifest: 不存在（请先运行 build）")


def _corpus_audit() -> None:
    settings = get_settings()
    manifest_path = settings.rag_corpus_manifest_path
    summary_path = settings.rag_source_dir / "corpus_audit_summary.json"
    _, summary = write_corpus_manifest(
        settings.rag_source_dir,
        manifest_path,
        summary_path,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _activate(index_version: str, evaluation_report) -> None:
    settings = get_settings()
    validation = validate_candidate_index(
        settings,
        index_version,
        evaluation_report=evaluation_report,
    )
    pointer = activate_index(settings.rag_index_dir, index_version)
    print(json.dumps({"validation": validation, "active": pointer}, ensure_ascii=False, indent=2))


def _query(question: str) -> None:
    settings = get_settings()
    try:
        result, trace = RagService.from_settings(settings).retrieve_with_trace(question)
    except RagStoreError as exc:
        print(f"检索失败：{exc}")
        sys.exit(1)
    print(f"pipeline={trace.pipeline} fallback={trace.fallback_reason or 'none'}")
    for chunk in result.chunks:
        location = f"第{chunk.page}页" if chunk.page else f"网页 · {chunk.section or '正文'}"
        print(
            f"OK relevance={(chunk.relevance_score or chunk.similarity):.3f} "
            f"final={(chunk.final_score or chunk.similarity):.3f} {chunk.relative_path} "
            f"{location} chunk#{chunk.chunk_index}"
        )
        print(f"    {chunk.text[:160].replace(chr(10), ' ')}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="app.rag.cli", description="本地 RAG 建库与检索命令")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="从 RAG/**/*.pdf 与 RAG/**/*.md 重建索引并写 manifest")
    subparsers.add_parser(
        "build-v2",
        help="从 corpus manifest/Docling 产物构建隔离的 V2 candidate index",
    )
    subparsers.add_parser("inspect", help="读取 manifest 与 collection 统计（不加载模型）")
    subparsers.add_parser(
        "corpus-audit",
        help="扫描 PDF/Markdown/DOCX 并生成 corpus manifest（不修改索引）",
    )
    query_parser = subparsers.add_parser("query", help="加载模型并打印 Top-K 检索结果")
    query_parser.add_argument("question", help="要检索的问题")
    activate_parser = subparsers.add_parser(
        "activate",
        help="通过 validation/eval gate 后原子切换 active index",
    )
    activate_parser.add_argument("index_version")
    activate_parser.add_argument("--evaluation-report", type=Path, required=True)
    graph_build_parser = subparsers.add_parser(
        "graph-build", help="从指定 V2 candidate 的 chunks.jsonl 构建图产物"
    )
    graph_build_parser.add_argument("index_version")
    graph_inspect_parser = subparsers.add_parser(
        "graph-inspect", help="校验 active 或指定 V2 index 的图产物"
    )
    graph_inspect_parser.add_argument("index_version", nargs="?")
    args = parser.parse_args(argv)
    if args.command == "build":
        _build()
    elif args.command == "build-v2":
        _build_v2()
    elif args.command == "inspect":
        _inspect()
    elif args.command == "query":
        _query(args.question)
    elif args.command == "corpus-audit":
        _corpus_audit()
    elif args.command == "activate":
        _activate(args.index_version, args.evaluation_report)
    elif args.command == "graph-build":
        _graph_build(args.index_version)
    elif args.command == "graph-inspect":
        _graph_inspect(args.index_version)


if __name__ == "__main__":
    main()
