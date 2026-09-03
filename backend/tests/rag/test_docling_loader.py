import json

from app.rag.corpus import CorpusDocument
from app.rag.docling_loader import load_docling_documents


def _document() -> CorpusDocument:
    return CorpusDocument(
        doc_id="doc_abc",
        title="接种指南",
        filename="指南.pdf",
        relative_path="政策/指南.pdf",
        content_hash="hash",
        source_type="official_document",
        issuer="疾控中心",
        authority_level=4,
        evidence_level="guideline",
        publication_date="2026-01-01",
        publication_year=2026,
        effective_date=None,
        version="2026年版",
        language="zh",
        topic="政策",
        review_status="existing_approved",
        is_superseded=False,
        duplicate_of=None,
        parse_status="parsed",
        page_count=2,
    )


def test_docling_loader_preserves_heading_page_and_table(tmp_path) -> None:
    payload = {
        "body": {"children": [
            {"$ref": "#/texts/0"},
            {"$ref": "#/texts/1"},
            {"$ref": "#/tables/0"},
        ]},
        "groups": [],
        "texts": [
            {"label": "section_header", "level": 1, "text": "接种实施", "prov": [{"page_no": 2}]},
            {"label": "text", "text": "接种前核对健康状况。", "prov": [{"page_no": 2}]},
        ],
        "tables": [{
            "label": "table",
            "prov": [{"page_no": 2}],
            "data": {"table_cells": [
                {
                    "start_row_offset_idx": 0,
                    "end_row_offset_idx": 1,
                    "start_col_offset_idx": 0,
                    "end_col_offset_idx": 1,
                    "text": "疫苗",
                },
                {
                    "start_row_offset_idx": 0,
                    "end_row_offset_idx": 1,
                    "start_col_offset_idx": 1,
                    "end_col_offset_idx": 2,
                    "text": "月龄",
                },
            ]},
        }],
    }
    (tmp_path / "doc_abc.json").write_text(json.dumps(payload), encoding="utf-8")

    pages, report = load_docling_documents([_document()], tmp_path)

    assert report.docling_files_loaded == 1
    assert pages[0].page == 2
    assert pages[0].section_path == ("接种实施",)
    assert pages[1].atomic is True
    assert pages[1].text == "[表格]\n疫苗 | 月龄"
