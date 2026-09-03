#!/usr/bin/env python3
"""Validate that a checkout has everything required for a production deploy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

SOURCE_FILES = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "nginx" / "default.conf",
    BACKEND_DIR / "Dockerfile",
    BACKEND_DIR / ".env.example",
    BACKEND_DIR / "pyproject.toml",
    BACKEND_DIR / "app" / "main.py",
    REPO_ROOT / "frontend" / "Dockerfile",
    REPO_ROOT / "frontend" / "package.json",
    REPO_ROOT / "frontend" / "pnpm-lock.yaml",
    REPO_ROOT / "frontend" / "src" / "main.tsx",
    REPO_ROOT / "RAG" / "corpus_manifest.jsonl",
)

INDEX_FILES = (
    "chunks.jsonl",
    "dense_records.jsonl",
    "dense_store.json",
    "manifest.json",
    "vectors.npy",
)

GRAPH_FILES = (
    "edges.json",
    "extraction_report.json",
    "metadata.json",
    "nodes.json",
    "provenance.json",
)

PLACEHOLDERS = {
    "",
    "changeme",
    "change_me",
    "replace_me",
    "your_api_key_here",
}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_json(path: Path, errors: list[str], label: str) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"{label} 无法读取或不是有效 JSON: {path.relative_to(REPO_ROOT)}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label} 顶层必须是 JSON object: {path.relative_to(REPO_ROOT)}")
        return None
    return value


def require_file(path: Path, errors: list[str], label: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        errors.append(f"缺少或为空的{label}: {path.relative_to(REPO_ROOT)}")


def require_directory(path: Path, errors: list[str], label: str) -> None:
    if not path.is_dir():
        errors.append(f"缺少{label}目录: {path.relative_to(REPO_ROOT)}")


def model_cache_path(model_name: str) -> Path:
    return BACKEND_DIR / "model_cache" / f"models--{model_name.replace('/', '--')}"


def validate_source(errors: list[str]) -> None:
    for path in SOURCE_FILES:
        require_file(path, errors, "源码文件")
    for nested_git in (BACKEND_DIR / ".git", REPO_ROOT / "frontend" / ".git"):
        if nested_git.exists():
            errors.append(f"检测到不应存在的嵌套 Git 元数据: {nested_git.relative_to(REPO_ROOT)}")


def validate_runtime(errors: list[str]) -> None:
    env_path = BACKEND_DIR / ".env"
    require_file(env_path, errors, "生产环境配置")
    env = parse_env(env_path) if env_path.is_file() else {}
    if env_path.is_file():
        api_key = env.get("DASHSCOPE_API_KEY", "").strip().lower()
        if api_key in PLACEHOLDERS:
            errors.append("DASHSCOPE_API_KEY 未配置或仍是占位值")

        admin_values = {
            key: env.get(key, "").strip()
            for key in ("ADMIN_USERNAME", "ADMIN_PASSWORD_HASH", "ADMIN_SESSION_SECRET")
        }
        if any(admin_values.values()) and not all(admin_values.values()):
            errors.append("管理员配置必须同时提供用户名、密码哈希和会话密钥")
        if admin_values["ADMIN_SESSION_SECRET"] and len(admin_values["ADMIN_SESSION_SECRET"]) < 32:
            errors.append("ADMIN_SESSION_SECRET 至少需要 32 个字符")

    active_path = BACKEND_DIR / "rag_index" / "active.json"
    require_file(active_path, errors, "RAG 活动版本指针")
    active = read_json(active_path, errors, "RAG 活动版本指针") if active_path.is_file() else None
    index_version = active.get("index_version") if active is not None else None
    if active is not None and (not isinstance(index_version, str) or not index_version.strip()):
        errors.append("RAG 活动版本指针缺少 index_version")
    if isinstance(index_version, str) and index_version.strip():
        index_dir = BACKEND_DIR / "rag_index" / "versions" / index_version
        require_directory(index_dir, errors, "RAG 版本")
        for name in INDEX_FILES:
            require_file(index_dir / name, errors, "RAG 版本文件")

        manifest_path = index_dir / "manifest.json"
        manifest = (
            read_json(manifest_path, errors, "RAG manifest")
            if manifest_path.is_file()
            else None
        )
        if manifest is not None and manifest.get("index_version") != index_version:
            errors.append("RAG manifest 的 index_version 与 active.json 不一致")

    embedding_model = env.get("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    require_directory(model_cache_path(embedding_model), errors, "Embedding 模型缓存")
    reranker_enabled = env.get("RAG_RERANKER_ENABLED", "true").lower() not in {"0", "false", "no"}
    if reranker_enabled:
        reranker_model = env.get("RAG_RERANKER_MODEL", "BAAI/bge-reranker-base")
        require_directory(model_cache_path(reranker_model), errors, "Reranker 模型缓存")

    graph_version = active.get("graph_version") if active is not None else None
    if isinstance(graph_version, str) and graph_version.strip():
        graph_dir = BACKEND_DIR / "runtime" / "graph" / "versions" / graph_version
        require_directory(graph_dir, errors, "知识图谱版本")
        for name in GRAPH_FILES:
            require_file(graph_dir / name, errors, "知识图谱版本文件")
        metadata_path = graph_dir / "metadata.json"
        metadata = (
            read_json(metadata_path, errors, "知识图谱 metadata")
            if metadata_path.is_file()
            else None
        )
        if metadata is not None and metadata.get("graph_version") != graph_version:
            errors.append("知识图谱 metadata 的 graph_version 与 active.json 不一致")
        if metadata is not None and metadata.get("knowledge_base_version") != index_version:
            errors.append("知识图谱绑定的知识库版本与 active.json 不一致")

    for path, label in (
        (BACKEND_DIR / "runtime", "运行时"),
        (BACKEND_DIR / "generated_images", "生成图片"),
    ):
        require_directory(path, errors, label)
        if path.is_dir() and os.name != "nt" and not os.access(path, os.W_OK):
            errors.append(f"当前用户不可写{label}目录: {path.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-only",
        action="store_true",
        help="只检查 Git 克隆应包含的源码，不要求私密运行时资产",
    )
    args = parser.parse_args()

    errors: list[str] = []
    validate_source(errors)
    if not args.source_only:
        validate_runtime(errors)

    if errors:
        print("部署预检失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    scope = "源码" if args.source_only else "源码与运行时资产"
    print(f"部署预检通过：{scope}完整。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
