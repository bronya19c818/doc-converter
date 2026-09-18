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


def test_front_matter_metadata_is_structured_in_fixed_display_order() -> None:
    source = """---
title: 项目方案
subtitle: 实施说明
organization: XX公司
department: XX部门
authors:
  - 张三
  - 李四
date: 2026-09-18
---

# 一、建设背景

正文。
"""

    result = normalize_markdown(source, filename="方案.md", confirmed_roles={})

    assert result.metadata == {
        "title": "项目方案",
        "subtitle": "实施说明",
        "organization": "XX公司",
        "department": "XX部门",
        "authors": ["张三", "李四"],
        "date": "2026-09-18",
    }
    assert result.markdown.index("title:") < result.markdown.index("subtitle:")
    assert result.markdown.index("organization:") < result.markdown.index("department:")
    assert result.markdown.index("authors:") < result.markdown.index("date:")


def test_unconfirmed_heading_stays_in_working_copy_and_suggestion_is_not_required() -> None:
    result = normalize_markdown(
        "# 项目方案\n\n正文。\n",
        filename="方案.md",
        confirmed_roles={},
    )

    assert "# 项目方案" in result.markdown
    assert result.metadata == {}
    assert result.report["integrity"]["passed"] is True


def test_leading_subtitle_abstract_and_keywords_are_extracted() -> None:
    source = """---
title: “人工智能+”行动下全国公共资源交易数智化发展实践与方向研究
---

基于14个省级“AI+公共资源交易”创新样本

摘要：在安全、制度和生态四个方面推进智慧交易。

关键词：人工智能；大模型；公共资源交易；数智化

# 一、引言

正文含有 **重点**、[链接](https://example.com) 和 ![图](images/a.png)。

| 项目 | 数量 |
| --- | ---: |
| A | 10 |
"""

    result = normalize_markdown(source, filename="研究.md", confirmed_roles={})

    assert result.metadata["subtitle"] == "基于14个省级“AI+公共资源交易”创新样本"
    assert result.metadata["abstract"] == "在安全、制度和生态四个方面推进智慧交易。"
    assert result.metadata["keywords"] == ["人工智能", "大模型", "公共资源交易", "数智化"]
    assert "摘要：" not in result.markdown
    assert "关键词：" not in result.markdown
    assert "# 一、引言" in result.markdown
    assert result.report["integrity"]["passed"] is True
    assert {change["to"] for change in result.report["changes"]} >= {
        "document-subtitle",
        "abstract",
        "keywords",
    }


def test_explicit_metadata_wins_over_leading_blocks() -> None:
    source = """---
title: 项目方案
subtitle: Front Matter 副标题
abstract: Front Matter 摘要
keywords:
  - 甲
  - 乙
---

正文开头不应被移动。

摘要：正文摘要不应覆盖。

关键词：正文；关键词
"""

    result = normalize_markdown(source, filename="方案.md", confirmed_roles={})

    assert result.metadata["subtitle"] == "Front Matter 副标题"
    assert result.metadata["abstract"] == "Front Matter 摘要"
    assert result.metadata["keywords"] == ["甲", "乙"]
    assert "正文开头不应被移动。" in result.markdown
    assert "摘要：正文摘要不应覆盖。" in result.markdown
    assert "关键词：正文；关键词" in result.markdown


def test_leading_plain_sentence_is_not_silently_moved_to_subtitle() -> None:
    source = """---
title: 项目方案
---

本方案将围绕业务目标、实施路径和保障措施展开说明。

# 一、建设背景
"""

    result = normalize_markdown(source, filename="方案.md", confirmed_roles={})

    assert "本方案将围绕业务目标、实施路径和保障措施展开说明。" in result.markdown
    assert "subtitle" not in result.metadata
