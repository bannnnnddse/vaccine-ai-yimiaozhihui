from app.rag.models import RetrievedChunk
from app.rag.ranking import apply_quality_prior, select_diverse


def _chunk(
    chunk_id: str,
    relevance: float,
    *,
    authority: int,
    evidence: str,
    document: str | None = None,
    superseded: bool = False,
    text: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        file_name=f"{chunk_id}.pdf",
        relative_path=f"{chunk_id}.pdf",
        page=1,
        chunk_index=0,
        text=text or f"{chunk_id} 的独立证据内容",
        source_hash=chunk_id,
        parent_doc_id=document or chunk_id,
        content_hash=f"hash-{chunk_id}",
        authority_level=authority,
        evidence_level=evidence,
        is_superseded=superseded,
        relevance_score=relevance,
    )


def test_authority_breaks_a_close_relevance_tie() -> None:
    paper = _chunk("paper", 0.80, authority=2, evidence="cohort")
    guideline = _chunk("guideline", 0.78, authority=4, evidence="guideline")

    ranked = apply_quality_prior("当前接种程序是什么？", [paper, guideline])

    assert ranked[0].id == "guideline"


def test_relevance_still_beats_an_unrelated_authoritative_source() -> None:
    paper = _chunk("paper", 0.92, authority=2, evidence="cohort")
    official = _chunk("official", 0.62, authority=4, evidence="guideline")

    ranked = apply_quality_prior("某疫苗队列研究结果", [official, paper])

    assert ranked[0].id == "paper"
    assert ranked[0].final_score > ranked[1].final_score


def test_superseded_document_is_excluded_unless_query_is_historical() -> None:
    old = _chunk(
        "old",
        0.95,
        authority=4,
        evidence="guideline",
        superseded=True,
    )
    current = _chunk("current", 0.80, authority=4, evidence="guideline")

    assert [item.id for item in apply_quality_prior("现行接种程序", [old, current])] == [
        "current"
    ]
    assert {item.id for item in apply_quality_prior("2016 年旧版程序历史", [old, current])} == {
        "old",
        "current",
    }


def test_year_alone_does_not_make_a_superseded_source_historical() -> None:
    old = _chunk(
        "old",
        0.99,
        authority=4,
        evidence="guideline",
        superseded=True,
    )

    assert apply_quality_prior("2026 年现行接种程序", [old]) == []


def test_final_score_remains_a_normalized_snapshot_value() -> None:
    strong = _chunk("strong", 0.99, authority=4, evidence="guideline")

    ranked = apply_quality_prior("现行接种程序", [strong])

    assert ranked[0].final_score == 1.0


def test_diversity_is_soft_and_avoids_one_document_occupying_all_results() -> None:
    candidates = [
        _chunk(f"a{index}", 0.9 - index / 100, authority=4, evidence="guideline", document="a")
        for index in range(4)
    ]
    candidates.append(_chunk("b1", 0.7, authority=2, evidence="cohort", document="b"))

    selected = select_diverse(candidates, top_k=4, max_chunks_per_document=2)

    assert [item.parent_doc_id for item in selected].count("a") == 3
    assert any(item.parent_doc_id == "b" for item in selected)
