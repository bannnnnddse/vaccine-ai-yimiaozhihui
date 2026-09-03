from datetime import datetime, timezone
from uuid import uuid4

from app.knowledge_gap.models import (
    InternalEvidenceSnapshot,
    KnowledgeGap,
    PubMedEvidenceSnapshot,
)
from app.knowledge_gap.repository import KnowledgeGapRepository
from app.pubmed.models import PubMedArticle
from app.rag.service import RetrievalResult
from app.services.evidence_assessment import EvidenceAssessmentResult


class KnowledgeGapService:
    """Creates pending review candidates without publishing knowledge."""

    def __init__(self, repository: KnowledgeGapRepository) -> None:
        self._repository = repository

    async def capture_candidate(
        self,
        *,
        original_query: str,
        rewritten_query: str,
        retrieval: RetrievalResult,
        assessment: EvidenceAssessmentResult,
        pubmed_articles: list[PubMedArticle],
    ) -> KnowledgeGap | None:
        if assessment.status == "sufficient":
            return None
        if assessment.status == "partial" and not pubmed_articles:
            return None

        gap = KnowledgeGap(
            id=uuid4().hex,
            original_query=original_query,
            rewritten_query=rewritten_query,
            internal_evidence=[
                InternalEvidenceSnapshot(
                    file_name=chunk.file_name,
                    page=chunk.page,
                    source_type=chunk.source_type,
                    source_url=chunk.source_url,
                    similarity=chunk.final_score or chunk.relevance_score or chunk.similarity,
                    excerpt=chunk.text[:1200],
                    relative_path=chunk.relative_path,
                    source_title=chunk.source_title,
                    section=chunk.section,
                )
                for chunk in retrieval.chunks[:10]
            ],
            assessment_status=assessment.status,
            assessment_reason=assessment.reason,
            missing_aspects=assessment.missing_aspects,
            pubmed_pmids=list(dict.fromkeys(article.pmid for article in pubmed_articles))[:20],
            pubmed_evidence=[
                PubMedEvidenceSnapshot(
                    pmid=article.pmid,
                    title=article.title,
                    abstract_excerpt=article.abstract[:2000],
                    journal=article.journal,
                    year=article.publication_year,
                    doi=article.doi,
                    url=article.url or f"https://pubmed.ncbi.nlm.nih.gov/{article.pmid}/",
                )
                for article in pubmed_articles[:20]
            ],
            candidate_claims=[],
            trigger_reason=assessment.trigger_reason or f"assessment_{assessment.status}",
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        return await self._repository.create(gap)
