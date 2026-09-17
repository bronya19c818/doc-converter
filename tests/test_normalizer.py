from doc_converter.normalizer import normalize_markdown


def test_confirmed_document_title_is_moved_to_front_matter() -> None:
    source = "# 项目建设方案\n\n# 一、建设背景\n\n正文内容。\n"

    result = normalize_markdown(
        source,
        filename="项目建设方案.md",
        confirmed_roles={1: "document-title"},
    )

    assert result.markdown.startswith("---\nschema: normalized-md/v1\ntitle: 项目建设方案\n---")
    assert "# 一、建设背景" in result.markdown
    assert "# 项目建设方案" not in result.markdown
    assert result.report["changes"] == [
        {"line": 1, "from": "heading-1", "to": "document-title"}
    ]


def test_normalization_preserves_image_link_table_and_body_text() -> None:
    source = """# 方案标题

正文含有 [项目链接](https://example.com/project)。

![库区布局](images/layout.png)

| 项目 | 数量 |
| --- | ---: |
| A | 10 |
"""

    result = normalize_markdown(source, filename="方案标题.md", confirmed_roles={1: "document-title"})

    assert result.report["integrity"]["passed"] is True
    assert result.report["integrity"]["images"] == ["images/layout.png"]
    assert result.report["integrity"]["links"] == ["https://example.com/project"]
    assert "| A | 10 |" in result.markdown
