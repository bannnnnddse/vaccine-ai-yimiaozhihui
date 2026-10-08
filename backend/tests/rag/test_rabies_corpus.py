"""Offline checks for the official rabies guideline and its governed RAG transcription."""

import json
import re
from hashlib import sha256
from pathlib import Path

from app.rag.chunking import split_structured_document
from app.rag.corpus import load_corpus_manifest
from app.rag.structured_loader import load_structured_markdown

ROOT = Path(__file__).resolve().parents[3]
RELATIVE = "国家政策与免疫规划/狂犬病暴露预防处置工作规范（2023年版）.md"


def _document():
    return next(document for document in load_corpus_manifest(
        ROOT / "RAG/corpus_manifest.jsonl"
    ) if document.relative_path == RELATIVE)


def test_official_rabies_source_identity_and_archive_integrity():
    document = _document()
    record = json.loads((ROOT / "docs/sources/rabies-2023/source_record.json").read_text(
        encoding="utf-8"
    ))
    assert document.authority_level == 4
    assert document.evidence_level == "guideline"
    assert document.publication_date == "2023-09-13"
    assert document.version == "2023年版"
    assert "国家卫生健康委员会办公厅" in document.issuer
    assert record["official_pdf_url"].startswith("https://www.chinacdc.cn/")
    assert sha256((ROOT / "docs/sources/rabies-2023/official.pdf").read_bytes()).hexdigest() == (
        record["pdf_sha256"]
    )
    assert sha256((ROOT / "RAG" / RELATIVE).read_bytes()).hexdigest() == (
        document.content_hash
    ) == record["markdown_sha256"]


def test_transcription_retains_all_articles_and_distinguishes_exposure_context():
    text = (ROOT / "RAG" / RELATIVE).read_text(encoding="utf-8")
    articles = re.findall(r"^### (第[一二三四五六七八九十]+条)$", text, re.MULTILINE)
    assert len(articles) == len(set(articles)) == 30
    assert len(re.findall(r"^## 第[一二三四五]+章", text, re.MULTILINE)) == 5
    assert "无明显出血的轻微抓伤、擦伤为Ⅱ级暴露" in text
    assert "暴露后狂犬病疫苗接种无禁忌症" in text
    assert "妊娠妇女" in text and "推迟暴露前免疫" in text
    assert "对胎儿没有影响" not in text


def test_existing_markdown_loader_preserves_article_provenance_and_supported_claims():
    document = _document()
    sections, report = load_structured_markdown(ROOT / "RAG", [document])
    assert not report.warnings
    chunks = [chunk for section in sections for chunk in split_structured_document(
        section, chunk_size=600, chunk_overlap=100, start_index=section.block_index * 100
    )]
    assert chunks and all(chunk.parent_doc_id == document.doc_id for chunk in chunks)
    assert all(chunk.source_url.startswith("https://www.chinacdc.cn/") for chunk in chunks)
    assert all(chunk.page is None for chunk in chunks)
    assert any("第十九条" in chunk.section and "接种无禁忌症" in chunk.text for chunk in chunks)
    assert any("第二十七条" in chunk.section and "3个月" in chunk.text for chunk in chunks)
