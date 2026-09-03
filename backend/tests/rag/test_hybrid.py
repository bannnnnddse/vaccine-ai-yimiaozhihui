from dataclasses import replace

from app.rag.hybrid import Bm25Index, reciprocal_rank_fusion
from app.rag.models import RetrievedChunk, TextChunk


def _text_chunk(chunk_id: str, text: str) -> TextChunk:
    return TextChunk(chunk_id, f"{chunk_id}.pdf", f"{chunk_id}.pdf", 1, 0, text, chunk_id)


def _dense(chunk_id: str, similarity: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id,
        f"{chunk_id}.pdf",
        f"{chunk_id}.pdf",
        1,
        0,
        chunk_id,
        chunk_id,
        similarity=similarity,
    )


def test_bm25_prefers_exact_medical_keyword() -> None:
    index = Bm25Index([
        _text_chunk("exact", "EV71 灭活疫苗预防 EV71 感染所致手足口病"),
        _text_chunk("broad", "儿童疫苗可以预防多种感染性疾病"),
    ])

    results = index.query("EV71 疫苗", top_k=2)

    assert results[0].id == "exact"
    assert results[0].lexical_rank == 1
    assert results[0].lexical_score > results[1].lexical_score


def test_bm25_indexes_governed_document_metadata_and_skips_zero_match_results() -> None:
    index = Bm25Index([
        TextChunk(
            "com-cov2",
            "Com-COV2研究中异源COVID疫苗接种计划.pdf",
            "source.pdf",
            1,
            0,
            "研究正文使用英文标题。",
            "source",
            source_title="Persistence of immune response",
        ),
        _text_chunk("other", "儿童疫苗可以预防多种感染性疾病"),
    ])

    results = index.query("Com-COV2", top_k=2)

    assert [item.id for item in results] == ["com-cov2"]
    assert index.query("不存在的检索词", top_k=2) == []


def test_rrf_merges_rankings_without_adding_incompatible_scores() -> None:
    dense = [_dense("dense-only", 0.9), _dense("both", 0.8)]
    lexical = [replace(_dense("both", 0.0), lexical_score=12.0)]

    results = reciprocal_rank_fusion(dense, lexical, rrf_k=60)

    assert results[0].id == "both"
    assert results[0].dense_rank == 2
    assert results[0].lexical_rank == 1
    assert results[0].rrf_score == 1 / 62 + 1 / 61
