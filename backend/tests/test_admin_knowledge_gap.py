import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.api.routes.chat import get_qwen_service
from app.core.config import Settings
from app.knowledge_gap.models import (
    CandidateClaim,
    KnowledgeGap,
    PubMedEvidenceSnapshot,
)
from app.knowledge_gap.repository import SqliteKnowledgeGapRepository
from app.main import create_app
from app.rag.service import RagService
from app.services.conversation_router import ConversationRoute, ConversationRouteDecision
from app.services.knowledge_gap_review_service import (
    KnowledgeGapPublishError,
    KnowledgeGapReviewService,
)
from app.services.qwen_service import VaccineQuestionAnalysis


class FakeEmbedder:
    model_name = "fake-embedder"

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [
            1.0 if "中和抗体" in text else 0.0,
            1.0 if "HPV" in text else 0.0,
            0.1,
        ]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "dashscope_api_key": None,
        "rag_source_dir": tmp_path / "RAG",
        "rag_index_dir": tmp_path / "rag_index",
        "rag_model_cache_dir": tmp_path / "model_cache",
        "rag_embedding_model": "fake-embedder",
        "rag_min_similarity": 0.0,
        "app_database_path": tmp_path / "runtime" / "app.db",
        "knowledge_draft_dir": tmp_path / "runtime" / "knowledge_drafts",
    }
    values.update(overrides)
    return Settings(**values)


def _gap() -> KnowledgeGap:
    return KnowledgeGap(
        id="gap123",
        original_query="HPV 疫苗如何产生保护？",
        rewritten_query="HPV 疫苗 中和抗体 保护机制",
        assessment_status="partial",
        assessment_reason="内部资料缺少机制证据。",
        missing_aspects=["中和抗体"],
        pubmed_pmids=["12345678"],
        pubmed_evidence=[PubMedEvidenceSnapshot(
            pmid="12345678",
            title="HPV vaccine neutralizing antibodies",
            abstract_excerpt="Vaccination induces neutralizing antibodies.",
            journal="Vaccine",
            year=2025,
            doi="10.1000/example",
            url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        )],
        trigger_reason="assessment_partial",
        created_at=datetime.now(timezone.utc),
    )


async def _approved_service(
    tmp_path: Path,
    **setting_overrides,
) -> tuple[KnowledgeGapReviewService, KnowledgeGap]:
    settings = _settings(tmp_path, **setting_overrides)
    repository = SqliteKnowledgeGapRepository(settings.app_database_path)
    rag_service = RagService.from_settings(settings)
    service = KnowledgeGapReviewService(settings, repository, rag_service)
    gap = await repository.create(_gap())
    claim = CandidateClaim(text="HPV 疫苗可诱导中和抗体形成保护。", evidence_pmids=["12345678"])
    reviewed = await service.save_review(
        gap.id,
        version=gap.version,
        reviewer_note="文献支持该机制。",
        candidate_claims=[claim],
        actor="admin",
    )
    approved = await service.approve(
        gap.id,
        version=reviewed.version,
        title="HPV 疫苗的中和抗体保护机制",
        reviewer_note="文献支持该机制。",
        candidate_claims=[claim],
        actor="admin",
    )
    return service, approved


@pytest.mark.asyncio
async def test_approved_generates_preview_without_touching_rag(tmp_path: Path) -> None:
    service, approved = await _approved_service(tmp_path)

    gap, content = await service.read_draft(approved.id)

    assert gap.status == "approved"
    assert "HPV 疫苗可诱导中和抗体形成保护" in content
    assert "PMID 12345678" in content
    assert not service._settings.rag_source_dir.exists()
    assert not service._settings.rag_index_dir.exists()


@pytest.mark.asyncio
async def test_publish_reuses_ingestion_and_is_retrievable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.rag.builder.BgeEmbedder", FakeEmbedder)
    monkeypatch.setattr("app.rag.service.BgeEmbedder", FakeEmbedder)
    service, approved = await _approved_service(tmp_path)

    published = await service.publish(approved.id, version=approved.version, actor="admin")
    result = service._rag_service.retrieve("HPV 疫苗中和抗体")

    assert published.status == "published"
    assert published.published_relative_path == "人工审核发布/gap123.md"
    assert any(item.source_type == "curated" for item in result.sources)
    assert any("中和抗体" in item.content for item in result.sources)


@pytest.mark.asyncio
async def test_publish_builds_validated_graph_before_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.rag.builder.BgeEmbedder", FakeEmbedder)
    monkeypatch.setattr("app.rag.service.BgeEmbedder", FakeEmbedder)
    service, approved = await _approved_service(tmp_path, graph_rag_enabled=True)

    published = await service.publish(approved.id, version=approved.version, actor="admin")
    active = service._settings.rag_index_dir / "active.json"
    active_version = json.loads(active.read_text(encoding="utf-8"))["index_version"]
    graph_dir = service._settings.rag_index_dir / "versions" / active_version / "graph"

    assert published.status == "published"
    assert (graph_dir / "manifest.json").is_file()
    assert (graph_dir / "nodes.json").is_file()
    assert (graph_dir / "edges.json").is_file()
    assert (graph_dir / "provenance.json").is_file()


@pytest.mark.asyncio
async def test_publish_failure_keeps_approved_and_removes_formal_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, approved = await _approved_service(tmp_path)

    def fail_build(*_args, **_kwargs):
        raise RuntimeError("embedding failed")

    monkeypatch.setattr(
        "app.services.knowledge_gap_review_service.build_candidate_index", fail_build
    )
    with pytest.raises(KnowledgeGapPublishError):
        await service.publish(approved.id, version=approved.version, actor="admin")

    current = await service.repository.get(approved.id)
    assert current.status == "approved"
    assert not (service._settings.rag_source_dir / "人工审核发布" / "gap123.md").exists()


def test_admin_session_and_review_list_are_protected(tmp_path: Path) -> None:
    password_hash = PasswordHasher(time_cost=1, memory_cost=8192).hash("correct horse")
    settings = _settings(
        tmp_path,
        admin_username="review-admin",
        admin_password_hash=password_hash,
        admin_session_secret="s" * 32,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/api/v1/admin/knowledge-gaps").status_code == 401
        login = client.post(
            "/api/v1/admin/session",
            json={"username": "review-admin", "password": "correct horse"},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        listing = client.get("/api/v1/admin/knowledge-gaps")
        assert listing.status_code == 200
        assert listing.json()["items"] == []
        assert client.delete("/api/v1/admin/session").status_code == 403
        assert client.delete(
            "/api/v1/admin/session", headers={"X-CSRF-Token": csrf}
        ).status_code == 204


def test_chat_uses_the_newly_published_curated_knowledge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    monkeypatch.setattr("app.rag.builder.BgeEmbedder", FakeEmbedder)
    monkeypatch.setattr("app.rag.service.BgeEmbedder", FakeEmbedder)
    service, approved = asyncio.run(_approved_service(tmp_path))
    asyncio.run(service.publish(approved.id, version=approved.version, actor="admin"))

    settings = service._settings.model_copy(update={"pubmed_enabled": False})
    app = create_app(settings)
    qwen = AsyncMock()
    qwen.classify_conversation_route.return_value = ConversationRouteDecision(
        route=ConversationRoute.KNOWLEDGE_OR_OTHER,
        needs_rag=True,
        retrieval_query="HPV 疫苗中和抗体",
        rewrite_status="not_needed",
    )
    qwen.analyze_question.return_value = VaccineQuestionAnalysis(
        is_vaccine_related=True,
        answer="新发布知识说明 HPV 疫苗可诱导中和抗体。",
        session_id="response-published",
    )
    app.dependency_overrides[get_qwen_service] = lambda: qwen

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "HPV 疫苗如何保护？"})

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["source_type"] == "curated"
    assert source["file_name"] == "gap123.md"
    assert "中和抗体" in source["content"]
