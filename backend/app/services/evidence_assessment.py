import logging
import re
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.pubmed.query import extract_named_identifiers
from app.rag.models import RetrievedChunk
from app.rag.service import RetrievalResult

logger = logging.getLogger(__name__)

EvidenceStatus = Literal["sufficient", "partial", "insufficient", "conflict"]
AssessmentMethod = Literal["rule", "llm", "hybrid"]

_EXTERNAL_EVIDENCE_PATTERN = re.compile(
    r"最新|近期研究|最近研究|最新研究|文献|临床试验|随机对照|系统综述|"
    r"pubmed|\brct\b|meta[ -]?analysis|systematic review|clinical trial",
    re.IGNORECASE,
)
_COMPLEX_COVERAGE_PATTERN = re.compile(
    r"、|以及|并且|同时|分别|比较|区别|还是|能持续多久|持续时间|一方面|另一方面"
)
_CLEAR_COVERAGE_PATTERN = re.compile(
    r"几月龄|什么时候|哪一版|哪个版本|哪一种|有什么作用|是什么|"
    r"怎么照顾|如何护理|通常几天|是否可以|能否|可以吗|安全吗|安全性如何"
)


class EvidenceSemanticAssessment(BaseModel):
    status: EvidenceStatus
    reason: str = Field(min_length=1, max_length=1000)
    missing_aspects: list[str] = Field(default_factory=list, max_length=10)


class EvidenceAssessmentResult(EvidenceSemanticAssessment):
    should_search_pubmed: bool
    trigger_reason: str | None = Field(default=None, max_length=300)
    assessment_method: AssessmentMethod


class EvidenceSemanticAssessor(Protocol):
    async def assess_local_evidence(
        self,
        query: str,
        retrieval: RetrievalResult,
    ) -> EvidenceSemanticAssessment: ...


class EvidenceAssessmentService:
    """Assess local Top-K evidence without expanding the router's responsibilities."""

    def __init__(
        self,
        semantic_assessor: EvidenceSemanticAssessor | None = None,
        *,
        rule_min_top_score: float = 0.90,
        rule_min_support_score: float = 0.80,
    ) -> None:
        self._semantic_assessor = semantic_assessor
        self._rule_min_top_score = rule_min_top_score
        self._rule_min_support_score = rule_min_support_score

    async def assess(
        self,
        query: str,
        retrieval: RetrievalResult,
    ) -> EvidenceAssessmentResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("evidence assessment query cannot be blank")

        explicitly_requests_external_evidence = bool(
            _EXTERNAL_EVIDENCE_PATTERN.search(normalized_query)
        )
        if not retrieval.chunks:
            return EvidenceAssessmentResult(
                status="insufficient",
                reason="本地检索没有返回达到最低相关性阈值的有效证据。",
                missing_aspects=["缺少可用于回答当前问题的本地证据"],
                should_search_pubmed=True,
                trigger_reason=(
                    "explicit_external_evidence_request"
                    if explicitly_requests_external_evidence
                    else "no_internal_evidence"
                ),
                assessment_method="rule",
            )

        if explicitly_requests_external_evidence:
            return EvidenceAssessmentResult(
                status="partial",
                reason="用户明确要求动态或研究文献证据，本地静态知识不能覆盖该时效性要求。",
                missing_aspects=["用户要求的最新或外部研究证据"],
                should_search_pubmed=True,
                trigger_reason="explicit_external_evidence_request",
                assessment_method="rule",
            )

        missing_identifiers = _missing_required_identifiers(
            normalized_query,
            retrieval,
        )
        if missing_identifiers:
            return EvidenceAssessmentResult(
                status="partial",
                reason="本地证据没有出现问题中的关键病原体或疫苗产品标识，无法验证专门结论。",
                missing_aspects=[
                    f"关键标识符“{identifier}”的专门证据"
                    for identifier in missing_identifiers
                ],
                should_search_pubmed=True,
                trigger_reason="missing_required_identifiers",
                assessment_method="rule",
            )

        if self._has_clear_high_confidence_coverage(normalized_query, retrieval):
            return EvidenceAssessmentResult(
                status="sufficient",
                reason="多条本地证据的检索与重排分数达到明确充分阈值。",
                missing_aspects=[],
                should_search_pubmed=False,
                trigger_reason="high_confidence_local_evidence",
                assessment_method="rule",
            )

        if self._semantic_assessor is None:
            return self._conservative_fallback("semantic_assessor_unavailable")

        try:
            semantic = await self._semantic_assessor.assess_local_evidence(
                normalized_query,
                retrieval,
            )
        except Exception as exc:
            logger.warning("本地证据语义评估失败，采用保守回退: %s", type(exc).__name__)
            return self._conservative_fallback("semantic_assessment_failed")

        should_search = semantic.status != "sufficient"
        return EvidenceAssessmentResult(
            **semantic.model_dump(),
            should_search_pubmed=should_search,
            trigger_reason=(f"assessment_{semantic.status}" if should_search else None),
            assessment_method="hybrid",
        )

    @staticmethod
    def _conservative_fallback(trigger_reason: str) -> EvidenceAssessmentResult:
        return EvidenceAssessmentResult(
            status="partial",
            reason="无法可靠完成语义覆盖判断，按证据可能不完整处理。",
            missing_aspects=["本地证据对问题的语义覆盖尚未确认"],
            should_search_pubmed=True,
            trigger_reason=trigger_reason,
            assessment_method="rule",
        )

    def _has_clear_high_confidence_coverage(
        self,
        query: str,
        retrieval: RetrievalResult,
    ) -> bool:
        if (
            len(query) > 120
            or _COMPLEX_COVERAGE_PATTERN.search(query)
            or not _CLEAR_COVERAGE_PATTERN.search(query)
        ):
            return False
        if len(retrieval.chunks) < 2:
            return False
        scores = [_evidence_score(chunk) for chunk in retrieval.chunks]
        return (
            scores[0] >= self._rule_min_top_score
            and max(scores[1:]) >= self._rule_min_support_score
        )


def _missing_required_identifiers(
    query: str,
    retrieval: RetrievalResult,
) -> list[str]:
    """Return named biomedical/product identifiers absent from local evidence.

    Exact matching is deliberately used only as a guard against false
    sufficiency.  It does not claim that an identifier alone makes evidence
    sufficient; the semantic assessment still evaluates all other questions.
    """

    identifiers = extract_named_identifiers(query)
    if not identifiers:
        return []
    evidence = " ".join(
        " ".join(
            part
            for part in (chunk.file_name, chunk.title, chunk.text)
            if part
        )
        for chunk in retrieval.chunks
    ).casefold()
    return sorted(
        identifier
        for identifier in identifiers
        if identifier.casefold() not in evidence
    )


def _evidence_score(chunk: RetrievedChunk) -> float:
    if chunk.relevance_score is not None:
        return chunk.relevance_score
    return chunk.similarity
