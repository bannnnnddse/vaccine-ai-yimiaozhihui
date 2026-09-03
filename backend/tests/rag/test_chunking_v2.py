from app.rag.chunking import split_structured_document
from app.rag.models import PageDocument


def test_structure_aware_chunk_keeps_title_section_and_stable_provenance() -> None:
    document = PageDocument(
        file_name="指南.pdf",
        relative_path="政策/指南.pdf",
        page=12,
        text="完整禁忌症说明，不应与标题分离。",
        source_hash="source",
        doc_id="doc-stable",
        title="预防接种指南",
        section="第三章 > 接种禁忌",
        section_path=("第三章", "接种禁忌"),
        authority_level=4,
        evidence_level="guideline",
    )

    first = split_structured_document(
        document, chunk_size=200, chunk_overlap=20, start_index=0
    )[0]
    rebuilt = split_structured_document(
        document, chunk_size=200, chunk_overlap=20, start_index=99
    )[0]

    assert first.id == rebuilt.id
    assert first.parent_doc_id == "doc-stable"
    assert first.section_path == ("第三章", "接种禁忌")
    assert "文档：预防接种指南" in first.embedding_text
    assert "章节：第三章 > 接种禁忌" in first.embedding_text


def test_table_rows_stay_together_until_atomic_limit() -> None:
    document = PageDocument(
        "表格.pdf",
        "表格.pdf",
        2,
        "[表格]\n疫苗 | 月龄\n乙肝 | 0月龄\n百白破 | 2月龄",
        "hash",
        atomic=True,
        block_type="table",
    )

    chunks = split_structured_document(
        document,
        chunk_size=20,
        chunk_overlap=5,
        start_index=0,
        atomic_max_chars=35,
    )

    assert all(chunk.text.startswith("[表格]") for chunk in chunks)
    assert any("乙肝 | 0月龄" in chunk.text for chunk in chunks)


def test_identical_blocks_on_one_page_have_stable_distinct_ids() -> None:
    values = {
        "file_name": "指南.pdf",
        "relative_path": "指南.pdf",
        "page": 1,
        "text": "同一段文字",
        "source_hash": "source",
        "doc_id": "doc-stable",
        "section_path": ("同一章节",),
    }
    first = PageDocument(**values, block_index=1)
    second = PageDocument(**values, block_index=2)

    first_chunk = split_structured_document(
        first, chunk_size=600, chunk_overlap=100, start_index=0
    )[0]
    second_chunk = split_structured_document(
        second, chunk_size=600, chunk_overlap=100, start_index=1
    )[0]

    assert first_chunk.id != second_chunk.id
    assert first_chunk.id == split_structured_document(
        first, chunk_size=600, chunk_overlap=100, start_index=99
    )[0].id
