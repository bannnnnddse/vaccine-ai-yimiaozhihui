from app.rag.models import PageDocument
from app.rag.text import clean_text, split_page


def test_clean_text_removes_nulls_and_collapses_layout_noise() -> None:
    assert clean_text("疫\x00苗   接种\n\n\n注意事项") == "疫苗 接种\n\n注意事项"


def test_split_page_keeps_page_metadata_and_overlap() -> None:
    page = PageDocument(
        file_name="指南.pdf",
        relative_path="政策/指南.pdf",
        page=12,
        text="第一句疫苗知识。第二句接种知识。第三句不良反应。第四句处理方法。",
        source_hash="abc123",
    )

    chunks = split_page(page, chunk_size=22, chunk_overlap=6, start_index=0)

    assert len(chunks) >= 2
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.page == 12 for chunk in chunks)
    assert all(chunk.file_name == "指南.pdf" for chunk in chunks)
    assert all(chunk.relative_path == "政策/指南.pdf" for chunk in chunks)
    assert all(chunk.text.strip() for chunk in chunks)


def test_split_page_rejects_invalid_overlap() -> None:
    page = PageDocument("指南.pdf", "指南.pdf", 1, "有效文本。", "hash")

    try:
        split_page(page, chunk_size=10, chunk_overlap=10, start_index=0)
    except ValueError as exc:
        assert str(exc) == "chunk_overlap must be smaller than chunk_size"
    else:
        raise AssertionError("expected ValueError")
