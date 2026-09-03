from pathlib import Path

from app.rag.markdown_loader import load_markdown_documents


def test_load_markdown_documents_preserves_official_metadata_and_sections(tmp_path: Path) -> None:
    path = tmp_path / "专题" / "免疫问答.md"
    path.parent.mkdir()
    path.write_text(
        """> 来源机构：中国疾病预防控制中心
>
> 原始标题：疫苗免疫预防（水痘）
>
> 原始链接：https://www.chinacdc.cn/example
>
> 发布日期：2026-06-22
>
> 文档类型：官方网页转存；内容以官网最新版本为准。

---

# 接种前注意事项

接种前应如实告知接种人员儿童的健康状况。

## 特殊健康状态

儿童存在特殊健康状态时，应由接种人员进行现场评估。
""",
        encoding="utf-8",
    )

    documents, report = load_markdown_documents(tmp_path)

    assert [(document.section, document.page) for document in documents] == [
        ("接种前注意事项", None),
        ("特殊健康状态", None),
    ]
    assert all(document.source_type == "web" for document in documents)
    assert all(document.source_url == "https://www.chinacdc.cn/example" for document in documents)
    assert all(document.source_title == "疫苗免疫预防（水痘）" for document in documents)
    assert all("来源机构" not in document.text for document in documents)
    assert report.markdown_files_seen == 1
    assert report.unique_markdown_files == 1
    assert report.markdown_sections_indexed == 2


def test_load_markdown_documents_skips_untraceable_file(tmp_path: Path) -> None:
    path = tmp_path / "无来源.md"
    path.write_text("# 接种提示\n\n请咨询接种人员。", encoding="utf-8")

    documents, report = load_markdown_documents(tmp_path)

    assert documents == []
    assert report.markdown_files_seen == 1
    assert report.unique_markdown_files == 1
    assert report.warnings == ["无来源.md 缺少可追溯的原始链接，已跳过"]
