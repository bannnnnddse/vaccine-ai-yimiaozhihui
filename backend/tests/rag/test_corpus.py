import json

from app.rag.corpus import scan_corpus, stable_document_id


def test_document_id_is_stable_for_normalized_relative_path() -> None:
    assert stable_document_id("政策\\指南.pdf") == stable_document_id("政策/指南.pdf")
    assert stable_document_id("政策/指南.pdf") != stable_document_id("政策/另一指南.pdf")


def test_corpus_manifest_records_exact_duplicate_and_cautious_metadata(tmp_path) -> None:
    content = """> 来源机构：中国疾病预防控制中心
>
> 原始标题：疫苗接种知识问答
>
> 原始链接：https://www.chinacdc.cn/example
>
> 发布日期：2026-01-02

# 接种建议

请依据现行接种程序进行接种。
"""
    first = tmp_path / "官方" / "问答.md"
    duplicate = tmp_path / "副本.md"
    first.parent.mkdir()
    first.write_text(content, encoding="utf-8")
    duplicate.write_text(content, encoding="utf-8")

    documents, summary = scan_corpus(tmp_path)

    assert len(documents) == 2
    assert summary["unique_content_count"] == 1
    assert summary["duplicate_file_count"] == 1
    canonical = next(item for item in documents if item.duplicate_of is None)
    copied = next(item for item in documents if item.duplicate_of is not None)
    assert copied.duplicate_of == canonical.doc_id
    assert canonical.source_type == "official_web"
    assert canonical.authority_level == 4
    assert canonical.publication_date == "2026-01-02"


def test_verified_override_can_correct_source_classification(tmp_path) -> None:
    document_path = tmp_path / "资料.md"
    document_path.write_text(
        "> 原始链接：https://example.org/source\n\n# 标题\n\n正文",
        encoding="utf-8",
    )
    (tmp_path / "corpus_overrides.json").write_text(
        json.dumps(
            {
                "overrides": {
                    "资料.md": {
                        "source_type": "official_document",
                        "issuer": "已核验机构",
                        "authority_level": 4,
                        "metadata_confidence": "high",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    documents, _ = scan_corpus(tmp_path)

    assert documents[0].source_type == "official_document"
    assert documents[0].issuer == "已核验机构"
    assert documents[0].authority_level == 4


def test_curated_publication_is_recorded_as_human_approved(tmp_path) -> None:
    (tmp_path / "gap.md").write_text(
        """> 来源机构：人工审核知识库
>
> 原始标题：审核知识
>
> 原始链接：https://pubmed.ncbi.nlm.nih.gov/1/
>
> 来源类型：curated

# 审核知识

人工确认正文。
""",
        encoding="utf-8",
    )

    documents, _ = scan_corpus(tmp_path)

    assert documents[0].source_type == "curated"
    assert documents[0].review_status == "human_approved"
