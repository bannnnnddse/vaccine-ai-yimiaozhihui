"""Explainable, conservative prefilter for GraphRAG extraction candidates.

The filter is deliberately a call-reduction step only: it never derives entities
or relations and never modifies the RAG chunk it receives.  Ambiguous chunks are
kept so that Validator V2 remains the sole medical-fact admission boundary.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.rag.models import TextChunk


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    """A per-chunk, auditable decision made before any LLM request."""

    candidate: bool
    reason: str


@dataclass(frozen=True, slots=True)
class CandidateFilterResult:
    """Candidate chunks and explicit counts suitable for extraction reports."""

    candidates: list[TextChunk]
    decisions: dict[str, CandidateDecision]
    candidate_count: int
    filtered_count: int
    filter_reasons: dict[str, int]


# These anchors identify text with plausible medical relations.  They are broad
# on purpose; a match retains the chunk rather than claiming that it is factual.
# The catalog includes both Chinese and English source material.  Keep a chunk
# whenever either language contains a medical anchor; filtering an ambiguous
# medical passage is much costlier than asking the existing strict validator to
# reject an unproductive candidate.
_MEDICAL_ANCHOR = re.compile(
    r"疫苗|感染|病原体|预防(?!接种工作)|风险|保护(?:效果|力)?|"
    r"剂次|年龄|禁忌|免疫|抗体|不良反应|副反应|接种程序|接种对象|"
    r"接种间隔|病原|抗原|疾病|病毒|细菌|"
    r"vaccine|vaccin(?:ation|ated|e)?|immuni[sz](?:ation|e[ds]?|ing)?|"
    r"antibod(?:y|ies)|antigen|pathogen|infect(?:ion|ed|ious)?|"
    r"disease|virus|viral|bacteri(?:um|a|al)|adverse(?:\s+event|\s+reaction)?|"
    r"contraindic(?:ation|ated)?|dose[sd]?|booster|efficacy|effectiveness|"
    r"seroconver(?:sion|ted)|reactogenicity|protect(?:ion|ive|ed)?",
    re.IGNORECASE,
)

_ADMINISTRATIVE = re.compile(
    r"目录|目\s*录|通知|公告|公示|联系人|联系电话|通信地址|邮编|"
    r"电子邮箱|机构职责|职责分工|管理流程|工作流程|审批|备案|报送|"
    r"接种单位|医疗机构|疾控(?:中心)?|行政|部门|办公室|设备(?:要求|管理)?|"
    r"冷链设备|采购|经费|会议"
)

_TOC_LINE = re.compile(r"^(?:第?[一二三四五六七八九十\d]+[、.]|\d+(?:\.\d+)+)\s*\S{0,80}$")


def classify_chunk(chunk: TextChunk) -> CandidateDecision:
    """Classify one unmodified chunk using deterministic, explainable rules."""

    text = re.sub(r"\s+", " ", chunk.text).strip()
    if not text:
        return CandidateDecision(candidate=False, reason="empty_text")
    if _TOC_LINE.fullmatch(text):
        return CandidateDecision(candidate=False, reason="table_of_contents")
    if _MEDICAL_ANCHOR.search(text):
        return CandidateDecision(candidate=True, reason="medical_relation_signal")
    if _ADMINISTRATIVE.search(text):
        return CandidateDecision(candidate=False, reason="administrative_or_operational")
    return CandidateDecision(candidate=False, reason="no_medical_relation_signal")


def filter_candidate_chunks(chunks: list[TextChunk]) -> CandidateFilterResult:
    """Return retained chunks and an auditable reason for every input chunk."""

    decisions = {chunk.id: classify_chunk(chunk) for chunk in chunks}
    candidates = [chunk for chunk in chunks if decisions[chunk.id].candidate]
    reasons = Counter(
        decision.reason for decision in decisions.values() if not decision.candidate
    )
    return CandidateFilterResult(
        candidates=candidates,
        decisions=decisions,
        candidate_count=len(candidates),
        filtered_count=len(chunks) - len(candidates),
        filter_reasons=dict(sorted(reasons.items())),
    )
