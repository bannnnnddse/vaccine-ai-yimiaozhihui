from hashlib import sha256

from app.graph.llm_extractor import (
    LLMBatchExtraction,
    LLMEntityCandidate,
    LLMRelationCandidate,
    validate_batch,
)
from app.rag.models import TextChunk


def _chunk(text: str) -> TextChunk:
    return TextChunk(
        id="chunk", file_name="test.md", relative_path="test.md", page=None,
        chunk_index=0, text=text, source_hash="source",
        content_hash=sha256(text.encode()).hexdigest(),
    )


def _prevents(chunk: TextChunk, target: str, target_type: str):
    return validate_batch(LLMBatchExtraction(
        entities=[
            LLMEntityCandidate(
                canonical_name="乙肝疫苗", entity_type="Vaccine", aliases=[],
                surface_form="乙肝疫苗", chunk_id=chunk.id,
            ),
            LLMEntityCandidate(
                canonical_name=target, entity_type=target_type, aliases=[],
                surface_form=target, chunk_id=chunk.id,
            ),
        ],
        relations=[LLMRelationCandidate(
            source_surface="乙肝疫苗", target_surface=target, relation_type="PREVENTS",
            evidence_quote=chunk.text, confidence=0.99, chunk_id=chunk.id,
        )],
    ), [chunk], 0.85)[0]


def test_v3_requires_explicit_prevention_cue_for_prevents() -> None:
    result = _prevents(_chunk("乙肝疫苗是儿童防御乙型肝炎的武器。"), "乙型肝炎", "Disease")
    assert result.relations == []
    assert "relation_evidence_cue_missing" in result.rejected


def test_v3_rejects_disease_endpoint_embedded_in_pathogen_phrase() -> None:
    result = _prevents(_chunk("乙肝疫苗可预防乙型肝炎病毒感染。"), "乙型肝炎", "Disease")
    assert result.relations == []
    assert "disease_endpoint_is_pathogen_context" in result.rejected


def test_v3_accepts_direct_prevention_evidence() -> None:
    result = _prevents(_chunk("乙肝疫苗可预防乙型肝炎。"), "乙型肝炎", "Disease")
    assert result.relations[0].relation_type == "PREVENTS"
