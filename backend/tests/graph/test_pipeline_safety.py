import pytest
from pydantic import ValidationError

from app.graph.llm_extractor import LLMRelationCandidate


@pytest.mark.parametrize("relation", ["IS_A", "PART_OF", "SUPPORTED_BY"])
def test_system_relations_cannot_enter_the_llm_relation_schema(relation: str) -> None:
    with pytest.raises(ValidationError):
        LLMRelationCandidate(
            source_surface="乙肝疫苗", target_surface="乙型肝炎", relation_type=relation,
            evidence_quote="乙肝疫苗可预防乙型肝炎。", confidence=0.99, chunk_id="chunk",
        )


def test_related_to_cannot_enter_the_llm_relation_schema() -> None:
    with pytest.raises(ValidationError):
        LLMRelationCandidate(
            source_surface="乙肝疫苗", target_surface="乙型肝炎", relation_type="RELATED_TO",
            evidence_quote="乙肝疫苗可预防乙型肝炎。", confidence=0.99, chunk_id="chunk",
        )
