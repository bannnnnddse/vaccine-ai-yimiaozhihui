from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_image_job_settings_have_explicit_defaults(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, generated_image_dir=tmp_path)

    assert settings.qwen_model == "qwen3.8-flash"
    assert settings.qwen_lightweight_model == "qwen3.8-flash"
    assert settings.generated_image_dir == tmp_path
    assert settings.reference_image_dir == Path("./assets/backend_references")
    assert settings.dashscope_image_model == "wan2.7-image-pro"
    assert settings.wan_image_size == "2K"
    assert settings.wan_edit_min_input_side_px == 240
    assert settings.wan_image_timeout_seconds == 300
    assert settings.image_job_concurrency == 1
    assert settings.image_job_ttl_seconds == 3600
    assert settings.image_soft_deadline_seconds == 120
    assert settings.image_hard_deadline_seconds == 150
    assert settings.enable_fast_image_refinement_pipeline is True
    assert settings.image_auto_revision_max == 3
    assert settings.image_critic_model == "qwen3.8-flash"
    assert settings.image_critic_auto_bbox_min_confidence == 0.85
    assert settings.image_edit_scope_guard_threshold == 0.05
    assert settings.image_edit_roi_padding_ratio == 0.20
    assert settings.image_edit_mask_feather_px == 12
    assert settings.image_edit_min_bbox_side_px == 4
    assert settings.image_edit_min_bbox_area_px == 64
    assert settings.image_edit_outside_pixel_tolerance == 0
    assert settings.image_edit_max_aspect_ratio_error == 0.05
    assert settings.image_edit_min_inside_change == 0.01
    assert settings.cell_ip_enabled is False
    assert settings.cell_ip_skill_dir.name == "cell-ip-illustrations"


def test_image_hard_deadline_must_exceed_soft_deadline() -> None:
    with pytest.raises(ValidationError, match="hard deadline"):
        Settings(_env_file=None, image_soft_deadline_seconds=150, image_hard_deadline_seconds=150)


def test_env_example_documents_image_settings_without_a_real_secret() -> None:
    contents = Path(".env.example").read_text(encoding="utf-8")

    assert "DASHSCOPE_API_KEY=your_api_key_here" in contents
    assert "QWEN_MODEL=qwen3.8-flash" in contents
    assert "QWEN_LIGHTWEIGHT_MODEL=qwen3.8-flash" in contents
    assert "DASHSCOPE_IMAGE_MODEL=wan2.7-image-pro" in contents
    assert "WAN_IMAGE_SIZE=2K" in contents
    assert "WAN_IMAGE_TIMEOUT_SECONDS=300" in contents
    assert "REFERENCE_IMAGE_DIR=./assets/backend_references" in contents
    assert "GENERATED_IMAGE_DIR=./generated_images" in contents
    assert "IMAGE_JOB_CONCURRENCY=1" in contents
    assert "IMAGE_JOB_TTL_SECONDS=3600" in contents
    assert "IMAGE_SOFT_DEADLINE_SECONDS=120" in contents
    assert "IMAGE_HARD_DEADLINE_SECONDS=150" in contents
    assert "IMAGE_CRITIC_MODEL=qwen3.8-flash" in contents
    assert "IMAGE_EDIT_SCOPE_GUARD_THRESHOLD=0.05" in contents
    assert "IMAGE_EDIT_MIN_INSIDE_CHANGE=0.01" in contents
    assert "CELL_IP_ENABLED=false" in contents
    assert "CELL_IP_SKILL_DIR=../skills/cell-ip-illustrations" in contents
    assert "RAG_WARMUP_ENABLED=false" in contents
    assert "RAG_MAX_CONCURRENT_RETRIEVALS=1" in contents
    assert "RAG_TORCH_NUM_THREADS=2" in contents
    assert "RAG_TORCH_INTEROP_THREADS=1" in contents
    assert "EVIDENCE_RULE_MIN_TOP_SCORE=0.90" in contents
    assert "EVIDENCE_RULE_MIN_SUPPORT_SCORE=0.80" in contents
    assert "RAG_DENSE_FETCH_K=50" in contents
    assert "RAG_LEXICAL_FETCH_K=50" in contents
    assert "RAG_FUSION_CANDIDATE_K=60" in contents
    assert "RAG_RERANK_CANDIDATE_K=60" in contents
    assert "RAG_WINDOW_RESCORE_ENABLED=true" in contents
    assert "RAG_NEIGHBOR_SMOOTH_LAMBDA=0.9" in contents
    assert "sk-" not in contents


def test_rag_defaults_point_to_project_corpus_and_backend_index() -> None:
    settings = Settings(_env_file=None, dashscope_api_key=None)

    assert settings.rag_source_dir.name == "RAG"
    assert settings.rag_index_dir.name == "rag_index"
    assert settings.rag_embedding_model == "BAAI/bge-small-zh-v1.5"
    assert settings.rag_chunk_size == 600
    assert settings.rag_chunk_overlap == 100
    assert settings.rag_top_k == 4
    assert settings.rag_fetch_k == 8
    assert settings.rag_min_similarity == 0.60
    assert settings.rag_pipeline == "hybrid_v2"
    assert settings.rag_dense_fetch_k == 50
    assert settings.rag_lexical_fetch_k == 50
    assert settings.rag_fusion_candidate_k == 60
    assert settings.rag_rerank_candidate_k == 60
    assert settings.rag_reranker_batch_size == 16
    assert settings.rag_reranker_max_length == 256
    assert settings.rag_min_relevance == 0.0
    assert settings.rag_window_rescore_enabled is True
    assert settings.rag_window_reranker_max_length == 512
    assert settings.rag_window_prev_chars == 300
    assert settings.rag_window_next_chars == 300
    assert settings.rag_window_reranker_batch_size == 8
    assert settings.rag_neighbor_smooth_lambda == 0.9
    assert settings.rag_warmup_enabled is False
    assert settings.rag_max_concurrent_retrievals == 1
    assert settings.rag_torch_num_threads == 2
    assert settings.rag_torch_interop_threads == 1
    assert settings.evidence_rule_min_top_score == 0.90
    assert settings.evidence_rule_min_support_score == 0.80
    assert settings.rag_reranker_model == "BAAI/bge-reranker-base"
    assert settings.rag_quality_prior_max_adjustment == 0.05
    assert settings.rag_max_chunks_per_document == 3
    assert settings.graph_rag_enabled is False
    assert settings.graph_max_hops == 2
    assert settings.graph_max_paths == 5
    assert settings.graph_context_max_chars == 1800
    assert settings.graph_extraction_timeout == 180
    assert settings.graph_extraction_workers == 2


def test_graph_context_budget_must_fit_inside_rag_context() -> None:
    with pytest.raises(ValidationError, match="Graph context budget"):
        Settings(
            _env_file=None,
            rag_max_context_chars=1000,
            graph_context_max_chars=1000,
        )


def test_custom_rag_source_keeps_generated_manifest_inside_that_corpus(
    tmp_path: Path,
) -> None:
    source = tmp_path / "isolated-rag"
    settings = Settings(_env_file=None, rag_source_dir=source)

    assert settings.rag_corpus_manifest_path == source / "corpus_manifest.jsonl"


def test_rag_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError, match="RAG chunk overlap"):
        Settings(_env_file=None, rag_chunk_size=300, rag_chunk_overlap=300)


def test_rag_fetch_k_must_cover_top_k() -> None:
    with pytest.raises(ValidationError, match="RAG fetch_k"):
        Settings(_env_file=None, rag_top_k=5, rag_fetch_k=4)


def test_rag_v2_candidate_pool_must_cover_reranker_and_top_k() -> None:
    with pytest.raises(ValidationError, match="fusion candidate pool"):
        Settings(_env_file=None, rag_fusion_candidate_k=7, rag_rerank_candidate_k=8)
    with pytest.raises(ValidationError, match="rerank candidates"):
        Settings(_env_file=None, rag_top_k=5, rag_rerank_candidate_k=4)


def test_evidence_rule_support_threshold_cannot_exceed_top_threshold() -> None:
    with pytest.raises(ValidationError, match="evidence support score"):
        Settings(
            _env_file=None,
            evidence_rule_min_top_score=0.80,
            evidence_rule_min_support_score=0.90,
        )


def test_pubmed_is_enabled_by_default_and_documents_safe_placeholders() -> None:
    settings = Settings(_env_file=None, dashscope_api_key=None)
    contents = Path(".env.example").read_text(encoding="utf-8")

    assert settings.pubmed_enabled is True
    assert settings.pubmed_provider == "mcp"
    assert settings.pubmed_mcp_url == "https://pubmed.caseyjhand.com/mcp"
    assert settings.pubmed_max_results == 5
    assert settings.pubmed_max_tool_rounds == 2
    assert settings.pubmed_create_knowledge_gap is False
    assert settings.app_database_path == Path("./runtime/app.db")
    assert settings.knowledge_draft_dir == Path("./runtime/knowledge_drafts")
    assert "PUBMED_ENABLED=true" in contents
    assert "GRAPH_RAG_ENABLED=false" in contents
    assert "GRAPH_MAX_HOPS=2" in contents
    assert "PUBMED_PROVIDER=mcp" in contents
    assert "NCBI_API_KEY=\n" in contents
    assert "APP_DATABASE_PATH=./runtime/app.db" in contents
    assert "ADMIN_PASSWORD_HASH=\n" in contents


def test_enabled_mcp_provider_requires_valid_http_url() -> None:
    with pytest.raises(ValidationError, match="PUBMED_MCP_URL is required"):
        Settings(_env_file=None, pubmed_enabled=True, pubmed_mcp_url=None)
    with pytest.raises(ValidationError, match=r"http\(s\)"):
        Settings(_env_file=None, pubmed_enabled=True, pubmed_mcp_url="file:///tmp/mcp")


def test_pubmed_proxy_requires_valid_http_url() -> None:
    with pytest.raises(ValidationError, match=r"PUBMED_PROXY_URL.*http\(s\)"):
        Settings(_env_file=None, pubmed_proxy_url="socks5://127.0.0.1:7890")


def test_knowledge_gap_store_must_stay_outside_rag_paths(tmp_path: Path) -> None:
    rag_source = tmp_path / "RAG"
    with pytest.raises(ValidationError, match="outside RAG"):
        Settings(
            _env_file=None,
            rag_source_dir=rag_source,
            app_database_path=rag_source / "app.db",
        )
