from doc_converter.normalizer import (
    _normalize_html_images,
    _normalize_html_sub_sup,
    normalize_markdown,
)


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


def test_normalization_tracks_inline_reference_html_and_split_line_images() -> None:
    source = """![inline](<images/inline.png> "inline title")

![full][full-image]

[full-image]: images/full.png

![collapsed][]

[collapsed]: images/collapsed.png

![images/shortcut.png]

[images/shortcut.png]: images/shortcut.png

<IMG src='images/html.png' alt='HTML image' />

![split line]
(images/split.png)
"""

    result = normalize_markdown(source, filename="图片引用.md", confirmed_roles={})

    assert result.report["integrity"]["images"] == [
        "images/inline.png",
        "images/full.png",
        "images/collapsed.png",
        "images/shortcut.png",
        "images/html.png",
        "images/split.png",
    ]
    assert result.report["integrity"]["passed"] is True


def test_html_image_normalization_leaves_inline_code_untouched() -> None:
    source = '`<img src="example.png">` and <IMG src="real.png" alt="real image">'

    normalized = _normalize_html_images(source)

    assert '`<img src="example.png">`' in normalized
    assert '![real image](<real.png>)' in normalized


def test_html_sub_sup_normalization_leaves_inline_code_untouched() -> None:
    normalized = _normalize_html_sub_sup('`<sub>code</sub>` and <sub>2</sub> and <sup>2</sup>')

    assert '`<sub>code</sub>`' in normalized
    assert '~2~' in normalized
    assert '^2^' in normalized


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


def test_leading_author_and_organization_department_are_extracted_deterministically() -> None:
    source = """---
title: AI模型助力提升物资采购质量
---

何宏山

重庆市公共资源交易中心

采购管理部

摘要：本文说明采购质量提升路径。

关键词：采购；质量；模型

# 一、正文

正文内容。
"""

    result = normalize_markdown(source, filename="采购质量.md", confirmed_roles={})

    assert result.metadata["authors"] == ["何宏山"]
    assert result.metadata["organization"] == "重庆市公共资源交易中心"
    assert result.metadata["department"] == "采购管理部"
    assert "何宏山" not in result.markdown.split("---", 2)[-1].split("# 一、正文", 1)[0]
    assert "重庆市公共资源交易中心" not in result.markdown.split("---", 2)[-1].split("# 一、正文", 1)[0]


def test_explicit_author_and_author_unit_labels_override_heuristics() -> None:
    source = """---
title: 标注优先
---

作者：李明

作者单位：华东采购有限公司

综合办公室

# 一、正文
"""

    result = normalize_markdown(source, filename="标注.md", confirmed_roles={})

    assert result.metadata["authors"] == ["李明"]
    assert result.metadata["organization"] == "华东采购有限公司"
    assert result.metadata["department"] == "综合办公室"


def test_title_heading_can_precede_title_area_metadata() -> None:
    source = """# 项目标题

何宏山

XX公司

采购部

# 一、正文
"""

    result = normalize_markdown(source, filename="标题.md", confirmed_roles={})

    assert result.metadata["authors"] == ["何宏山"]
    assert result.metadata["organization"] == "XX公司"
    assert result.metadata["department"] == "采购部"
    assert "# 项目标题" in result.markdown


def test_h1_name_after_front_matter_title_is_extracted_as_author() -> None:
    source = """---
title: 标题
---

# 华软钢

重庆市公共资源交易中心

采购管理部

# 一、正文
"""

    result = normalize_markdown(source, filename="标题.md", confirmed_roles={})

    assert result.metadata["authors"] == ["华软钢"]
    assert "# 华软钢" not in result.markdown
    assert "# 一、正文" in result.markdown


def test_title_area_date_is_extracted_without_explicit_front_matter() -> None:
    source = """---
title: 标题
---

张三丰

某某科技有限公司

综合办公室

2026年9月18日

# 一、正文
"""

    result = normalize_markdown(source, filename="标题.md", confirmed_roles={})

    assert result.metadata["authors"] == ["张三丰"]
    assert result.metadata["organization"] == "某某科技有限公司"
    assert result.metadata["department"] == "综合办公室"
    assert result.metadata["date"] == "2026年9月18日"


def test_raw_html_table_is_normalized_with_a_caption_boundary() -> None:
    source = """---
title: 表格方案
---

表1 选择AI编写工具时应考虑的几个因素

<table><tr><td>序号</td><td>因素</td><td>描述</td></tr><tr><td>1</td><td>功能性</td><td>工具是否具备自动生成模板、智能检查等功能</td></tr><tr><td>2</td><td>易用性</td><td>界面是否直观、使用是否方便</td></tr></table>

# 一、正文
"""

    result = normalize_markdown(source, filename="表格.md", confirmed_roles={})

    assert "表1 选择AI编写工具时应考虑的几个因素" in result.markdown
    assert "<table>" not in result.markdown
    assert "| 序号 | 因素 | 描述 |" in result.markdown
    assert "| 1 | 功能性 | 工具是否具备自动生成模板、智能检查等功能 |" in result.markdown


def test_flat_atx_headings_are_releveled_from_chinese_and_numeric_numbering() -> None:
    source = """# 采购数字化实施路径及典型场景

# （一）实施路径

# 1. 连接集成全量要素数据

正文。

# （1）数据治理要求

细节。
"""

    result = normalize_markdown(source, filename="采购方案.md", confirmed_roles={})

    assert "# 采购数字化实施路径及典型场景" in result.markdown
    assert "## （一）实施路径" in result.markdown
    assert "### 1. 连接集成全量要素数据" in result.markdown
    assert "#### （1）数据治理要求" in result.markdown
    assert any(change["to"] == "heading-level" for change in result.report["changes"])


def test_markdown_second_pass_removes_toc_and_duplicate_standard_header() -> None:
    source = """Q/GDW 1234—2024

# 目次

一、范围........1
二、要求........2

# 一、范围

Q/GDW 1234—2024

正文内容。
"""

    result = normalize_markdown(source, filename="标准.md", confirmed_roles={})

    assert "# 目次" not in result.markdown
    assert "一、范围........1" not in result.markdown
    assert result.markdown.count("Q/GDW 1234—2024") == 1
    assert any(change["to"] == "remove-toc" for change in result.report["changes"])
    assert any(change["to"] == "remove-duplicate-standard-code" for change in result.report["changes"])


def test_markdown_second_pass_repairs_an_obvious_cross_page_fragment() -> None:
    source = """# 方案标题

建立采购数字化目录动态调整机

制，确保目录及时更新。
"""

    result = normalize_markdown(source, filename="方案.md", confirmed_roles={})

    assert "建立采购数字化目录动态调整机制，确保目录及时更新。" in result.markdown
    assert any(change["to"] == "repair-broken-paragraph" for change in result.report["changes"])


def test_technical_standard_numbered_headings_support_bare_subheadings() -> None:
    source = """Q/GDW 1234—2024

# 1 范围

# 2 规范性引用文件

# 5 盘点分类

# 5.1 盘点范围

5.1.1 全面盘点
"""

    result = normalize_markdown(source, filename="标准.md", confirmed_roles={})

    assert "## 5 盘点分类" in result.markdown
    assert "### 5.1 盘点范围" in result.markdown
    assert "#### 5.1.1 全面盘点" in result.markdown


def test_technical_standard_bare_root_and_decimal_headings_are_promoted() -> None:
    source = """Q/GDW 1234—2024

1 范围

1.1 适用范围

1.1.1 特殊范围
"""

    result = normalize_markdown(source, filename="标准.md", confirmed_roles={})

    assert "## 1 范围" in result.markdown
    assert "### 1.1 适用范围" in result.markdown
    assert "#### 1.1.1 特殊范围" in result.markdown


def test_flattened_heading_siblings_keep_the_same_level() -> None:
    source = """# 方案

# 1. 第一项

正文。

# 2. 第二项

# （一）第一子项

# （二）第二子项

# （1）细分一

# （2）细分二
"""

    result = normalize_markdown(source, filename="方案.md", confirmed_roles={})

    assert "## 1. 第一项" in result.markdown
    assert "## 2. 第二项" in result.markdown
    assert "## （一）第一子项" in result.markdown
    assert "## （二）第二子项" in result.markdown
    assert "### （1）细分一" in result.markdown
    assert "### （2）细分二" in result.markdown


def test_plain_third_level_heading_after_chinese_parent_is_promoted() -> None:
    source = """# 四、建构求索

# （一）技术突破路径

1. “0”到“1”：行业垂域大模型与智能体的重点攻坚

行业垂域大模型通常建立在基础大模型之上。
"""

    result = normalize_markdown(source, filename="研究报告.md", confirmed_roles={})

    assert "### 1. “0”到“1”：行业垂域大模型与智能体的重点攻坚" in result.markdown


def test_plain_arabic_outline_uses_each_number_component_as_a_level() -> None:
    cases = [
        ("1 实施背景", """1 实施背景

1.1 项目背景

1.1.1 政策背景

1.1.1.1 上级要求
"""),
        ("1. 实施背景", """1. 实施背景

1.1 项目背景

1.1.1 政策背景

1.1.1.1 上级要求
"""),
    ]

    for root_heading, source in cases:
        result = normalize_markdown(source, filename="技术方案.md", confirmed_roles={})

        assert f"# {root_heading}" in result.markdown
        assert "## 1.1 项目背景" in result.markdown
        assert "### 1.1.1 政策背景" in result.markdown
        assert "#### 1.1.1.1 上级要求" in result.markdown


def test_plain_chinese_government_outline_includes_circled_children() -> None:
    source = """一、实施背景

（一）基本情况

1. 当前现状

（1）具体问题

①具体表现

②另一表现
"""

    result = normalize_markdown(source, filename="工作报告.md", confirmed_roles={})

    assert "# 一、实施背景" in result.markdown
    assert "## （一）基本情况" in result.markdown
    assert "### 1. 当前现状" in result.markdown
    assert "#### （1）具体问题" in result.markdown
    assert "##### ①具体表现" in result.markdown
    assert "##### ②另一表现" in result.markdown


def test_chapter_section_and_part_heading_families_follow_context() -> None:
    chapter_source = """第一章 实施背景

第一节 基本情况

一、现状分析

（一）业务现状
"""
    part_source = """第一部分 总体设计

第一章 技术方案

第一节 实施背景
"""

    chapter_result = normalize_markdown(chapter_source, filename="研究报告.md", confirmed_roles={})
    part_result = normalize_markdown(part_source, filename="成果报告.md", confirmed_roles={})

    assert "# 第一章 实施背景" in chapter_result.markdown
    assert "## 第一节 基本情况" in chapter_result.markdown
    assert "### 一、现状分析" in chapter_result.markdown
    assert "#### （一）业务现状" in chapter_result.markdown
    assert "# 第一部分 总体设计" in part_result.markdown
    assert "## 第一章 技术方案" in part_result.markdown
    assert "### 第一节 实施背景" in part_result.markdown


def test_piece_and_unit_markers_are_recognized_as_outer_sections() -> None:
    for part_marker in ("第一篇", "第一单元"):
        source = f"""{part_marker} 总体设计

第一章 技术方案
"""

        result = normalize_markdown(source, filename="成果报告.md", confirmed_roles={})

        assert f"# {part_marker} 总体设计" in result.markdown
        assert "## 第一章 技术方案" in result.markdown


def test_unnumbered_markdown_headings_keep_their_explicit_levels() -> None:
    source = """# 实施背景

## 建设目标

### 主要做法

#### 实施成效
"""

    result = normalize_markdown(source, filename="简版方案.md", confirmed_roles={})

    assert "# 实施背景" in result.markdown
    assert "## 建设目标" in result.markdown
    assert "### 主要做法" in result.markdown
    assert "#### 实施成效" in result.markdown


def test_numbered_lists_and_fenced_code_are_not_promoted_to_headings() -> None:
    source = """# 操作步骤

1. 检查所有待处理文件
2. 修复发现的问题

```markdown
1. 示例编号
```
"""

    result = normalize_markdown(source, filename="操作步骤.md", confirmed_roles={})

    assert "1. 检查所有待处理文件" in result.markdown
    assert "2. 修复发现的问题" in result.markdown
    assert "### 1. 检查所有待处理文件" not in result.markdown
    assert "```markdown\n1. 示例编号\n```" in result.markdown


def test_short_escaped_numbered_paragraph_is_promoted_to_heading() -> None:
    source = """# CASE-MANUAL-001 非样式化中文编号标题

1\\. 数字编号标题但使用普通正文样式 〔CASE-MANUAL-003〕
"""

    result = normalize_markdown(source, filename="压力测试.md", confirmed_roles={})

    assert "## 1. 数字编号标题但使用普通正文样式 〔CASE-MANUAL-003〕" in result.markdown


def test_unescaped_single_numbered_list_item_is_not_promoted() -> None:
    source = "# 操作步骤\n\n1. 单项列表内容"

    result = normalize_markdown(source, filename="列表.md", confirmed_roles={})

    assert "1. 单项列表内容" in result.markdown
    assert "## 1. 单项列表内容" not in result.markdown


def test_numbered_bare_heading_requires_short_text_and_text_ending() -> None:
    short = normalize_markdown(
        "# 根标题\n\n1\\. 短标题内容",
        filename="短标题.md",
        confirmed_roles={},
    )
    long_text = "1\\. " + "超过三十五字的普通编号段落" * 3
    long_result = normalize_markdown(
        f"# 根标题\n\n{long_text}",
        filename="长标题.md",
        confirmed_roles={},
    )
    punctuation_result = normalize_markdown(
        "# 根标题\n\n1\\. 以逗号结尾，",
        filename="标点.md",
        confirmed_roles={},
    )

    assert "## 1. 短标题内容" in short.markdown
    assert "## " not in long_result.markdown.split("---", 2)[-1]
    assert "## 1. 以逗号结尾" not in punctuation_result.markdown


def test_preprocess_line_mapping_keeps_confirmed_roles_on_original_lines() -> None:
    source = """---
title: 原始标题
---

# 目次

一、范围........1

# 项目真实标题

# 一、范围

正文。
"""

    result = normalize_markdown(
        source,
        filename="项目.md",
        confirmed_roles={9: "document-title"},
    )

    assert result.metadata["title"] == "项目真实标题"
    assert "# 项目真实标题" not in result.markdown


def test_toc_without_a_following_heading_and_fenced_code_are_preserved() -> None:
    toc_source = """# 目次

一、范围........1

正文仍然存在。
"""

    toc_result = normalize_markdown(toc_source, filename="目录.md", confirmed_roles={})

    assert "# 目次" in toc_result.markdown
    assert "正文仍然存在。" in toc_result.markdown

    source = """Q/GDW 1234—2024

# 1 范围

# 2 规范性引用文件

```markdown
Q/GDW 1234—2024
# 5.1 示例字段
5.1 示例字段
```
"""

    result = normalize_markdown(source, filename="标准.md", confirmed_roles={})

    assert "```markdown\nQ/GDW 1234—2024\n# 5.1 示例字段\n5.1 示例字段\n```" in result.markdown
