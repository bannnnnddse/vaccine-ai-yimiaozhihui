"""Deterministic recall-audit helpers for the candidate prefilter.

This module deliberately reports *potential* false negatives.  It is a broad
rule-based triage aid for an explicit human sample review, not a replacement for
medical annotation or Validator V2.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from app.graph.candidate_filter import CandidateFilterResult
from app.rag.models import TextChunk

_POTENTIAL_FACT_SIGNAL = re.compile(
    r"(?:疫苗|感染|病原体|免疫|抗体|抗原|不良反应|禁忌|疾病|病毒|"
    r"vaccine|vaccin|immun|antibod|antigen|pathogen|infect|disease|virus|"
    r"adverse|contraindic|booster|dose|efficacy|reactogenicity)"
    r".{0,180}?"
    r"(?:预防|保护|导致|引起|适用于|剂次|禁忌|激活|产生|中和|增加|降低|"
    r"prevent|protect|caus|indicat|dose|contraindic|activat|produc|neutraliz|"
    r"increas|decreas|reduc|induc|associat)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class PrefilterRecallAudit:
    sample_size: int
    potential_false_negatives: int
    potential_false_negative_rate: float
    sample_chunk_ids: tuple[str, ...]


def has_potential_medical_relation(chunk: TextChunk) -> bool:
    """Flag a broad, review-worthy relation cue without asserting a fact."""

    return bool(_POTENTIAL_FACT_SIGNAL.search(chunk.text))


def audit_filtered_sample(
    chunks: list[TextChunk],
    result: CandidateFilterResult,
    *,
    sample_size: int = 100,
    seed: int = 20260820,
) -> PrefilterRecallAudit:
    """Sample skipped chunks reproducibly and estimate review-worthy misses."""

    filtered = [chunk for chunk in chunks if not result.decisions[chunk.id].candidate]
    if sample_size < 1:
        raise ValueError("sample_size must be positive")
    sampled = random.Random(seed).sample(filtered, min(sample_size, len(filtered)))
    potential = sum(has_potential_medical_relation(chunk) for chunk in sampled)
    return PrefilterRecallAudit(
        sample_size=len(sampled),
        potential_false_negatives=potential,
        potential_false_negative_rate=potential / len(sampled) if sampled else 0.0,
        sample_chunk_ids=tuple(chunk.id for chunk in sampled),
    )
