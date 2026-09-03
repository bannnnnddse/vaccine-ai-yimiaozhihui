from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.knowledge_gap.models import CandidateClaim, KnowledgeGap
from app.knowledge_gap.repository import SqliteKnowledgeGapRepository
from app.rag.builder import build_candidate_index
from app.rag.corpus import write_corpus_manifest
from app.rag.index_versions import (
    activate_index,
    read_active_pointer,
    resolve_active_index,
    restore_active_index,
    version_directory,
)
from app.rag.service import RagService
from app.rag.validation import validate_candidate_index

if TYPE_CHECKING:
    from app.graph.jobs import GraphJob, GraphJobRepository
    from app.graph.snapshot import GraphSnapshotPipeline


class KnowledgeGapReviewError(RuntimeError):
    pass


class KnowledgeGapPublishError(KnowledgeGapReviewError):
    pass


class KnowledgeGapReviewService:
    def __init__(
        self,
        settings: Settings,
        repository: SqliteKnowledgeGapRepository,
        rag_service: RagService,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._rag_service = rag_service
        self._publish_lock = asyncio.Lock()

    @property
    def repository(self) -> SqliteKnowledgeGapRepository:
        return self._repository

    async def save_review(
        self,
        gap_id: str,
        *,
        version: int,
        reviewer_note: str,
        candidate_claims: list[CandidateClaim],
        actor: str,
    ) -> KnowledgeGap:
        gap = await self._repository.get(gap_id)
        self._validate_claims(gap, candidate_claims, require_claims=False)
        now = datetime.now(timezone.utc)
        updated = gap.model_copy(update={
            "candidate_claims": candidate_claims,
            "reviewer_note": reviewer_note.strip() or None,
            "status": "in_review",
            "reviewed_at": now,
        })
        return await self._repository.update(
            updated,
            expected_version=version,
            allowed_statuses={"pending", "in_review", "hold"},
            event_type="review_saved",
            actor=actor,
            details={"claim_count": len(candidate_claims)},
        )

    async def hold(
        self, gap_id: str, *, version: int, reviewer_note: str, actor: str
    ) -> KnowledgeGap:
        gap = await self._repository.get(gap_id)
        updated = gap.model_copy(update={
            "status": "hold",
            "reviewer_note": reviewer_note.strip(),
            "reviewed_at": datetime.now(timezone.utc),
        })
        return await self._repository.update(
            updated,
            expected_version=version,
            allowed_statuses={"in_review"},
            event_type="held",
            actor=actor,
        )

    async def reject(
        self, gap_id: str, *, version: int, reviewer_note: str, actor: str
    ) -> KnowledgeGap:
        gap = await self._repository.get(gap_id)
        updated = gap.model_copy(update={
            "status": "rejected",
            "reviewer_note": reviewer_note.strip(),
            "reviewed_at": datetime.now(timezone.utc),
        })
        return await self._repository.update(
            updated,
            expected_version=version,
            allowed_statuses={"in_review"},
            event_type="rejected",
            actor=actor,
        )

    async def approve(
        self,
        gap_id: str,
        *,
        version: int,
        title: str,
        reviewer_note: str,
        candidate_claims: list[CandidateClaim],
        actor: str,
    ) -> KnowledgeGap:
        gap = await self._repository.get(gap_id)
        self._validate_claims(gap, candidate_claims, require_claims=True)
        now = datetime.now(timezone.utc)
        content = self._render_markdown(
            gap,
            title=title.strip(),
            reviewer_note=reviewer_note.strip(),
            candidate_claims=candidate_claims,
            reviewed_at=now,
        )
        draft_path = self._safe_child(self._settings.knowledge_draft_dir, f"{gap.id}.md")
        await asyncio.to_thread(self._write_atomic, draft_path, content.encode("utf-8"))
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        updated = gap.model_copy(update={
            "candidate_claims": candidate_claims,
            "reviewer_note": reviewer_note.strip(),
            "status": "approved",
            "reviewed_at": now,
            "approved_at": now,
            "draft_file_name": draft_path.name,
            "draft_sha256": digest,
            "draft_generated_at": now,
        })
        try:
            return await self._repository.update(
                updated,
                expected_version=version,
                allowed_statuses={"in_review"},
                event_type="approved",
                actor=actor,
                details={"draft_sha256": digest},
            )
        except Exception:
            draft_path.unlink(missing_ok=True)
            raise

    async def read_draft(self, gap_id: str) -> tuple[KnowledgeGap, str]:
        gap = await self._repository.get(gap_id)
        path = self.draft_path(gap)
        content = await asyncio.to_thread(path.read_text, encoding="utf-8")
        self._verify_digest(gap, content.encode("utf-8"))
        return gap, content

    async def queue_publish(
        self,
        gap_id: str,
        *,
        version: int,
        actor: str,
        jobs: GraphJobRepository,
    ) -> GraphJob:
        gap = await self._repository.get(gap_id)
        if gap.status != "approved" or gap.version != version:
            raise KnowledgeGapReviewError("knowledge gap is not publishable")
        publishing = await self._repository.update(
            gap.model_copy(update={"status": "publishing"}),
            expected_version=version,
            allowed_statuses={"approved"},
            event_type="publish_queued",
            actor=actor,
        )
        try:
            return await jobs.enqueue(
                "publish",
                {"gap_id": gap_id, "version": publishing.version, "actor": actor},
                signature=f"publish:{gap_id}:{publishing.version}",
            )
        except Exception:
            await self.restore_publish_failure(
                gap_id,
                version=publishing.version,
                actor="system",
            )
            raise

    async def restore_publish_failure(
        self, gap_id: str, *, version: int, actor: str
    ) -> KnowledgeGap:
        gap = await self._repository.get(gap_id)
        return await self._repository.update(
            gap.model_copy(update={"status": "approved"}),
            expected_version=version,
            allowed_statuses={"publishing"},
            event_type="publish_failed",
            actor=actor,
        )

    async def publish(
        self,
        gap_id: str,
        *,
        version: int,
        actor: str,
        graph_pipeline: GraphSnapshotPipeline | None = None,
    ) -> KnowledgeGap:
        async with self._publish_lock:
            gap, content = await self.read_draft(gap_id)
            expected_status = "publishing" if graph_pipeline else "approved"
            if gap.status != expected_status or gap.version != version:
                raise KnowledgeGapReviewError("knowledge gap is not publishable")
            published_dir = self._safe_child(
                self._settings.rag_source_dir,
                self._settings.rag_published_subdir,
            )
            published_path = self._safe_child(published_dir, f"{gap.id}.md")
            relative_path = published_path.relative_to(
                self._settings.rag_source_dir.resolve()
            ).as_posix()
            corpus_manifest_path = self._settings.rag_corpus_manifest_path
            corpus_summary_path = self._settings.rag_source_dir / "corpus_audit_summary.json"
            manifest_backup = self._read_optional(corpus_manifest_path)
            summary_backup = self._read_optional(corpus_summary_path)
            _, previous_version = resolve_active_index(self._settings.rag_index_dir)
            previous_pointer = read_active_pointer(self._settings.rag_index_dir)
            activated = False
            try:
                await asyncio.to_thread(self._write_atomic, published_path, content.encode("utf-8"))
                await asyncio.to_thread(
                    write_corpus_manifest,
                    self._settings.rag_source_dir,
                    corpus_manifest_path,
                    corpus_summary_path,
                )
                index_manifest = await asyncio.to_thread(
                    build_candidate_index,
                    self._settings,
                    local_files_only=True,
                )
                index_version = str(index_manifest["index_version"])
                await asyncio.to_thread(
                    validate_candidate_index,
                    self._settings,
                    index_version,
                )
                candidate_service = RagService.for_index_version(
                    self._settings,
                    index_version,
                )
                retrieval = await asyncio.to_thread(
                    candidate_service.retrieve, gap.candidate_claims[0].text
                )
                if not any(chunk.relative_path == relative_path for chunk in retrieval.chunks):
                    raise KnowledgeGapPublishError("published knowledge was not retrievable")
                graph_version = None
                if graph_pipeline is not None:
                    graph_metadata = await graph_pipeline.build_for_index(
                        version_directory(self._settings.rag_index_dir, index_version),
                        index_version,
                        parent_graph_version=previous_pointer.get("graph_version"),
                        mode="incremental",
                    )
                    graph_version = str(graph_metadata["graph_version"])
                await asyncio.to_thread(
                    activate_index,
                    self._settings.rag_index_dir,
                    index_version,
                    graph_version,
                )
                activated = True
                published = gap.model_copy(update={
                    "status": "published",
                    "published_at": datetime.now(timezone.utc),
                    "published_relative_path": relative_path,
                })
                return await self._repository.update(
                    published,
                    expected_version=version,
                    allowed_statuses={expected_status},
                    event_type="published",
                    actor=actor,
                    details={
                        "relative_path": relative_path,
                        "sha256": gap.draft_sha256 or "",
                        "index_version": index_version,
                        "graph_version": graph_version or "",
                    },
                )
            except Exception as exc:
                published_path.unlink(missing_ok=True)
                self._restore_optional(corpus_manifest_path, manifest_backup)
                self._restore_optional(corpus_summary_path, summary_backup)
                if activated:
                    await asyncio.to_thread(
                        restore_active_index,
                        self._settings.rag_index_dir,
                        previous_version,
                        previous_pointer.get("graph_version"),
                    )
                if isinstance(exc, KnowledgeGapReviewError):
                    raise
                raise KnowledgeGapPublishError("knowledge publication failed") from exc

    def draft_path(self, gap: KnowledgeGap) -> Path:
        if not gap.draft_file_name or not gap.draft_sha256:
            raise KnowledgeGapReviewError("approved draft is missing")
        path = self._safe_child(self._settings.knowledge_draft_dir, gap.draft_file_name)
        if not path.is_file():
            raise KnowledgeGapReviewError("approved draft is missing")
        return path

    @staticmethod
    def _verify_digest(gap: KnowledgeGap, content: bytes) -> None:
        if hashlib.sha256(content).hexdigest() != gap.draft_sha256:
            raise KnowledgeGapReviewError("approved draft checksum mismatch")

    @staticmethod
    def _validate_claims(
        gap: KnowledgeGap, claims: list[CandidateClaim], *, require_claims: bool
    ) -> None:
        if require_claims and not claims:
            raise KnowledgeGapReviewError("at least one candidate claim is required")
        allowed_pmids = set(gap.pubmed_pmids)
        for claim in claims:
            if not set(claim.evidence_pmids).issubset(allowed_pmids):
                raise KnowledgeGapReviewError("candidate claim references unknown PMID")

    @staticmethod
    def _safe_child(parent: Path, name: str) -> Path:
        root = parent.resolve()
        candidate = (root / name).resolve()
        if candidate != root and root not in candidate.parents:
            raise KnowledgeGapReviewError("unsafe knowledge path")
        return candidate

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _read_optional(path: Path) -> bytes | None:
        return path.read_bytes() if path.is_file() else None

    @classmethod
    def _restore_optional(cls, path: Path, content: bytes | None) -> None:
        if content is None:
            path.unlink(missing_ok=True)
        else:
            cls._write_atomic(path, content)

    @staticmethod
    def _render_markdown(
        gap: KnowledgeGap,
        *,
        title: str,
        reviewer_note: str,
        candidate_claims: list[CandidateClaim],
        reviewed_at: datetime,
    ) -> str:
        evidence = {item.pmid: item for item in gap.pubmed_evidence}
        primary = candidate_claims[0].evidence_pmids[0]
        lines = [
            "> 来源机构：人工审核知识库",
            ">",
            f"> 原始标题：{title}",
            ">",
            f"> 原始链接：https://pubmed.ncbi.nlm.nih.gov/{primary}/",
            ">",
            "> 来源类型：curated",
            ">",
            "> 审核状态：人工审核已批准",
            ">",
            f"> 审核时间：{reviewed_at.isoformat()}",
            "",
            "---",
            "",
            f"# {title}",
            "",
            "## 经人工确认的知识主张",
            "",
        ]
        for index, claim in enumerate(candidate_claims, start=1):
            pmids = "、".join(f"PMID {pmid}" for pmid in claim.evidence_pmids)
            lines.extend([f"### 主张 {index}", "", claim.text, "", f"证据：{pmids}", ""])
        lines.extend(["## 完整参考文献", ""])
        referenced_pmids = (
            pmid for claim in candidate_claims for pmid in claim.evidence_pmids
        )
        for pmid in dict.fromkeys(referenced_pmids):
            article = evidence.get(pmid)
            if article:
                citation = f"- PMID {pmid}：{article.title}"
                if article.journal:
                    citation += f"；{article.journal}"
                if article.year:
                    citation += f"（{article.year}）"
                if article.doi:
                    citation += f"；DOI: {article.doi}"
                citation += f"；{article.url}"
            else:
                citation = f"- PMID {pmid}：https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            lines.append(citation)
        lines.extend(["", "## 审核说明", "", reviewer_note, ""])
        return "\n".join(lines)
