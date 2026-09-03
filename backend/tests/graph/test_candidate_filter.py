from app.graph.candidate_filter import classify_chunk, filter_candidate_chunks
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


def test_prefilter_excludes_administrative_chunk_without_medical_relation_signal() -> None:
    decision = classify_chunk(_chunk("admin", "接种单位应当落实设备管理和职责分工。"))

    assert decision.candidate is False
    assert decision.reason == "administrative_or_operational"


def test_prefilter_retains_medical_relation_chunk_and_reports_reasons() -> None:
    medical = _chunk("medical", "乙肝疫苗可预防乙型肝炎病毒感染，并产生保护效果。")
    administrative = _chunk("admin", "接种单位负责通知公告和联系人维护。")
    result = filter_candidate_chunks([medical, administrative])

    assert result.candidates == [medical]
    assert result.candidate_count == 1
    assert result.filtered_count == 1
    assert result.filter_reasons == {"administrative_or_operational": 1}
    assert result.decisions[medical.id].reason == "medical_relation_signal"


def test_prefilter_retains_english_medical_relation_chunk() -> None:
    decision = classify_chunk(
        _chunk("english", "The vaccine protects children against viral infection.")
    )

    assert decision.candidate is True
    assert decision.reason == "medical_relation_signal"
