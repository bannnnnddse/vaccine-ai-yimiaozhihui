from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "vaccine-ai-backend"
    app_env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    dashscope_api_key: str | None = Field(default=None, repr=False)
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.8-flash"
    qwen_lightweight_model: str = "qwen3.8-flash"
    dashscope_image_model: str = "wan2.7-image-pro"
    z_image_model: str = "z-image-turbo"
    z_image_endpoint: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    z_image_size: str = "1024*1024"
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    qwen_timeout_seconds: float = Field(default=60, gt=0)
    wan_image_size: str = "2K"
    wan_edit_min_input_side_px: int = Field(default=240, ge=240, le=8000)
    wan_image_timeout_seconds: float = Field(default=300, gt=0)
    z_image_timeout_seconds: float = Field(default=90, gt=0)

    generated_image_dir: Path = Path("./generated_images")
    reference_image_dir: Path = Path("./assets/backend_references")
    image_job_concurrency: int = Field(default=1, ge=1)
    image_job_ttl_seconds: int = Field(default=3600, ge=300)
    image_soft_deadline_seconds: int = Field(default=120, ge=30)
    image_hard_deadline_seconds: int = Field(default=150, ge=60)
    enable_fast_image_refinement_pipeline: bool = True
    # A reviewer may locate several independent labels.  Repair one bounded
    # region at a time and review again, rather than exposing the first draft.
    image_auto_revision_max: int = Field(default=3, ge=0, le=3)
    image_critic_model: str = "qwen3.8-flash"
    image_critic_auto_bbox_min_confidence: float = Field(default=0.85, ge=0, le=1)
    image_edit_model: str = "wan2.7-image-pro"
    image_edit_scope_guard_threshold: float = Field(default=0.05, ge=0, le=1)
    image_edit_min_inside_change: float = Field(default=0.01, ge=0, le=1)
    image_edit_roi_padding_ratio: float = Field(default=0.20, ge=0, le=1)
    image_edit_mask_feather_px: int = Field(default=12, ge=0, le=100)
    image_edit_min_bbox_side_px: int = Field(default=4, ge=1, le=512)
    image_edit_min_bbox_area_px: int = Field(default=64, ge=1)
    image_edit_outside_pixel_tolerance: int = Field(default=0, ge=0, le=255)
    image_edit_max_aspect_ratio_error: float = Field(default=0.05, ge=0, le=0.5)
    cell_ip_enabled: bool = False
    cell_ip_skill_dir: Path = _BACKEND_DIR.parent / "skills" / "cell-ip-illustrations"

    rag_source_dir: Path = _BACKEND_DIR.parent / "RAG"
    rag_index_dir: Path = _BACKEND_DIR / "rag_index"
    rag_model_cache_dir: Path = _BACKEND_DIR / "model_cache"
    rag_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_embedding_revision: str | None = None
    rag_embedding_device: str = "cpu"
    rag_collection_name: str = "vaccine_knowledge"
    rag_chunk_size: int = Field(default=600, ge=200, le=2000)
    rag_chunk_overlap: int = Field(default=100, ge=0, le=500)
    rag_top_k: int = Field(default=4, ge=1, le=10)
    rag_fetch_k: int = Field(default=8, ge=1, le=30)
    rag_min_similarity: float = Field(default=0.60, ge=0, le=1)
    rag_max_context_chars: int = Field(default=6000, ge=1000, le=12000)
    rag_pipeline: Literal["dense_v1", "hybrid_v2"] = "hybrid_v2"
    rag_corpus_manifest_path: Path = _BACKEND_DIR.parent / "RAG" / "corpus_manifest.jsonl"
    rag_docling_artifact_dir: Path = _BACKEND_DIR / "runtime" / "docling_v2"
    rag_chunking_version: str = "structure_v2_docling"
    rag_dense_fetch_k: int = Field(default=20, ge=1, le=100)
    rag_lexical_fetch_k: int = Field(default=20, ge=1, le=100)
    rag_fusion_candidate_k: int = Field(default=30, ge=1, le=100)
    rag_rrf_k: int = Field(default=60, ge=1, le=200)
    rag_bm25_k1: float = Field(default=1.5, gt=0, le=5)
    rag_bm25_b: float = Field(default=0.75, ge=0, le=1)
    rag_reranker_enabled: bool = True
    rag_reranker_model: str = "BAAI/bge-reranker-base"
    rag_reranker_revision: str | None = None
    rag_reranker_device: str = "cpu"
    rag_reranker_batch_size: int = Field(default=4, ge=1, le=64)
    rag_reranker_max_length: int = Field(default=256, ge=128, le=2048)
    rag_rerank_candidate_k: int = Field(default=8, ge=1, le=50)
    rag_min_relevance: float = Field(default=0.20, ge=0, le=1)
    rag_warmup_enabled: bool = False
    rag_max_concurrent_retrievals: int = Field(default=1, ge=1, le=8)
    rag_torch_num_threads: int = Field(default=2, ge=1, le=32)
    rag_torch_interop_threads: int = Field(default=1, ge=1, le=8)
    evidence_rule_min_top_score: float = Field(default=0.90, ge=0, le=1)
    evidence_rule_min_support_score: float = Field(default=0.80, ge=0, le=1)
    rag_quality_prior_max_adjustment: float = Field(default=0.05, ge=0, le=0.1)
    rag_quality_authority_share: float = Field(default=0.65, ge=0, le=1)
    rag_freshness_max_adjustment: float = Field(default=0.015, ge=0, le=0.05)
    rag_max_chunks_per_document: int = Field(default=2, ge=1, le=10)
    rag_near_duplicate_threshold: float = Field(default=0.94, ge=0.8, le=1)

    graph_rag_enabled: bool = False
    graph_max_hops: int = Field(default=2, ge=1, le=2)
    graph_max_paths: int = Field(default=5, ge=1, le=20)
    graph_context_max_chars: int = Field(default=1800, ge=300, le=6000)
    graph_schema_version: str = "vaccine_graph_v3"
    graph_extraction_rules_version: str = "vaccine_rules_v2"
    graph_build_enabled: bool = True
    graph_snapshot_dir: Path = Path("./runtime/graph")
    graph_extraction_model: str | None = None
    graph_extraction_min_confidence: float = Field(default=0.60, ge=0, le=1)
    graph_extraction_batch_size: int = Field(default=8, ge=1, le=16)
    graph_extraction_batch_chars: int = Field(default=12000, ge=1000, le=30000)
    graph_extraction_timeout: float = Field(default=180, gt=0, le=900)
    graph_extraction_workers: int = Field(default=2, ge=1, le=4)
    graph_extraction_prompt_version: str = "medical_graph_llm_v4_dense_batches"
    graph_validator_version: str = "medical_graph_validator_v10_dense_batches"
    graph_worker_lease_seconds: int = Field(default=900, ge=60, le=7200)
    graph_worker_poll_seconds: float = Field(default=2.0, ge=0.2, le=60)
    graph_visual_association_max_per_chunk: int = Field(default=3, ge=0, le=6)
    graph_visual_association_max_degree: int = Field(default=4, ge=0, le=8)

    pubmed_enabled: bool = True
    pubmed_provider: Literal["mcp", "direct"] = "mcp"
    pubmed_mcp_url: str | None = "https://pubmed.caseyjhand.com/mcp"
    pubmed_proxy_url: str | None = None
    ncbi_api_key: str | None = Field(default=None, repr=False)
    ncbi_email: str | None = Field(default=None, repr=False)
    ncbi_tool: str = "vaccine-ai-backend"
    pubmed_timeout_seconds: float = Field(default=20, gt=0, le=120)
    pubmed_max_results: int = Field(default=5, ge=1, le=20)
    pubmed_max_query_length: int = Field(default=500, ge=50, le=2000)
    pubmed_max_tool_rounds: int = Field(default=2, ge=1, le=2)
    pubmed_mcp_retries: int = Field(default=1, ge=0, le=3)
    pubmed_direct_retries: int = Field(default=1, ge=0, le=3)
    pubmed_create_knowledge_gap: bool = False
    app_database_path: Path = Path("./runtime/app.db")
    knowledge_draft_dir: Path = Path("./runtime/knowledge_drafts")
    rag_published_subdir: str = "人工审核发布"

    admin_username: str | None = None
    admin_password_hash: str | None = Field(default=None, repr=False)
    admin_session_secret: str | None = Field(default=None, repr=False)
    admin_session_ttl_seconds: int = Field(default=28800, ge=300, le=86400)
    admin_cookie_secure: bool = False

    @model_validator(mode="after")
    def validate_cross_field_settings(self) -> "Settings":
        if (
            "rag_source_dir" in self.model_fields_set
            and "rag_corpus_manifest_path" not in self.model_fields_set
        ):
            object.__setattr__(
                self,
                "rag_corpus_manifest_path",
                self.rag_source_dir / "corpus_manifest.jsonl",
            )
        if self.image_hard_deadline_seconds <= self.image_soft_deadline_seconds:
            raise ValueError("image hard deadline must exceed soft deadline")
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG chunk overlap must be smaller than chunk size")
        if self.rag_fetch_k < self.rag_top_k:
            raise ValueError("RAG fetch_k must be greater than or equal to top_k")
        if self.rag_fusion_candidate_k < self.rag_rerank_candidate_k:
            raise ValueError("RAG fusion candidate pool must cover rerank candidates")
        if self.rag_rerank_candidate_k < self.rag_top_k:
            raise ValueError("RAG rerank candidates must cover top_k")
        if self.evidence_rule_min_support_score > self.evidence_rule_min_top_score:
            raise ValueError("evidence support score cannot exceed the top score threshold")
        if self.graph_context_max_chars >= self.rag_max_context_chars:
            raise ValueError("Graph context budget must be smaller than total RAG context budget")
        if self.pubmed_enabled and self.pubmed_provider == "mcp":
            if not self.pubmed_mcp_url:
                raise ValueError("PUBMED_MCP_URL is required when MCP PubMed is enabled")
            parsed = urlparse(self.pubmed_mcp_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("PUBMED_MCP_URL must be an http(s) URL")
        if self.pubmed_proxy_url:
            parsed_proxy = urlparse(self.pubmed_proxy_url)
            if parsed_proxy.scheme not in {"http", "https"} or not parsed_proxy.netloc:
                raise ValueError("PUBMED_PROXY_URL must be an http(s) URL")
        protected_paths = (
            self.rag_source_dir.resolve(),
            self.rag_index_dir.resolve(),
            self.rag_model_cache_dir.resolve(),
        )
        runtime_paths = (self.app_database_path.resolve(), self.knowledge_draft_dir.resolve())
        if any(
            runtime_path == protected or protected in runtime_path.parents
            for runtime_path in runtime_paths
            for protected in protected_paths
        ):
            raise ValueError("KnowledgeGap runtime paths must stay outside RAG and indexes")
        admin_values = (self.admin_username, self.admin_password_hash, self.admin_session_secret)
        if any(admin_values) and not all(admin_values):
            raise ValueError(
                "ADMIN_USERNAME, ADMIN_PASSWORD_HASH and ADMIN_SESSION_SECRET are required together"
            )
        if self.admin_session_secret and len(self.admin_session_secret) < 32:
            raise ValueError("ADMIN_SESSION_SECRET must be at least 32 characters")
        published_subdir = Path(self.rag_published_subdir)
        if published_subdir.is_absolute() or ".." in published_subdir.parts:
            raise ValueError("RAG_PUBLISHED_SUBDIR must be a safe relative path")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def effective_graph_extraction_model(self) -> str:
        return self.graph_extraction_model or self.qwen_lightweight_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
