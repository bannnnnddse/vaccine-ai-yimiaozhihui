from app.graph.candidate_filter import filter_candidate_chunks
from app.graph.prefilter_audit import audit_filtered_sample, has_potential_medical_relation
from app.rag.models import TextChunk


def _chunk(identifier: str, text: str) -> TextChunk:
    return TextChunk(
        id=identifier,
        file_name="test.md",
        relative_path="test.md",
        page=None,
        chunk_index=0,
        text=text,
        source_hash="source",
    )


def test_audit_flags_review_worthy_medical_relation_signal() -> None:
    assert has_potential_medical_relation(
        _chunk("medical", "The vaccine protects against viral infection.")
    )
    assert not has_potential_medical_relation(_chunk("admin", "The office contact is listed."))


def test_audit_is_deterministic_and_samples_only_filtered_chunks() -> None:
    chunks = [
        _chunk("candidate", "乙肝疫苗可预防乙型肝炎。"),
        _chunk("skip-1", "The office contact is listed."),
        _chunk("skip-2", "Equipment maintenance is required."),
    ]
    result = filter_candidate_chunks(chunks)
    audit = audit_filtered_sample(chunks, result, sample_size=100, seed=7)

    assert audit.sample_size == 2
    assert set(audit.sample_chunk_ids) == {"skip-1", "skip-2"}
    assert audit.potential_false_negatives == 0
