from pathlib import Path

import pymupdf

from app.rag.pdf_loader import load_pdf_pages


def _write_pdf(path: Path, page_texts: list[str]) -> None:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text, fontname="china-s")
    document.save(path)


def test_load_pdf_pages_is_recursive_one_based_and_deduplicated(tmp_path: Path) -> None:
    nested = tmp_path / "分类"
    nested.mkdir()
    original = nested / "指南.pdf"
    duplicate = tmp_path / "指南副本.pdf"
    _write_pdf(original, ["第一页疫苗接种说明。", "第二页注意事项。"])
    duplicate.write_bytes(original.read_bytes())

    pages, report = load_pdf_pages(tmp_path, minimum_page_chars=5)

    assert [(page.file_name, page.page) for page in pages] == [
        ("指南.pdf", 1),
        ("指南.pdf", 2),
    ]
    assert report.pdf_files_seen == 2
    assert report.unique_pdf_files == 1
    assert report.pages_seen == 2
    assert report.pages_indexed == 2
    assert report.duplicate_pdf_files == ["指南副本.pdf"]


def test_load_pdf_pages_warns_and_skips_pages_without_text(tmp_path: Path) -> None:
    path = tmp_path / "扫描件.pdf"
    _write_pdf(path, [""])

    pages, report = load_pdf_pages(tmp_path, minimum_page_chars=50)

    assert pages == []
    assert report.pages_seen == 1
    assert report.pages_indexed == 0
    assert report.warnings == ["扫描件.pdf 第1页文本不足50字符，已跳过"]
