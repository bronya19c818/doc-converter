import zipfile

import pytest
from docx import Document
from docx.oxml.ns import qn

from doc_converter.docx_postprocess import _REFERENCE_HEADING_PATTERN
from doc_converter.renderer import render_docx, resolve_pandoc
from doc_converter.style_library import create_style_pack


def test_renderer_creates_editable_docx_from_normalized_markdown(tmp_path) -> None:
    markdown = """---
schema: normalized-md/v1
title: 项目建设方案
organization: XX公司
department: XX部门
---

# 一、建设背景

正文包含 **重点内容** 和 [项目链接](https://example.com)。

| 项目 | 数量 |
| --- | ---: |
| A | 10 |
"""
    output_path = tmp_path / "项目建设方案.docx"

    render_docx(
        markdown=markdown,
        style_pack=create_style_pack(name="测试样式", format_id="docx"),
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    document = Document(output_path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert output_path.exists()
    assert "项目建设方案" in text
    assert "一、建设背景" in text
    assert "重点内容" in text
    assert document.tables[0].cell(1, 1).text == "10"


def test_renderer_extracts_title_area_blocks_from_raw_markdown(tmp_path) -> None:
    markdown = """---
title: 原始 Markdown 标题
---

基于本地样本的实施说明

摘要：这是摘要内容。

关键词：确定性转换；DOCX；A4

# 一、正文

正文内容。
"""
    output_path = tmp_path / "raw.docx"

    render_docx(
        markdown=markdown,
        style_pack=create_style_pack(name="原始输入测试", format_id="docx"),
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    document = Document(output_path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "基于本地样本的实施说明" in text
    assert "摘要：这是摘要内容。" in text
    assert "关键词：确定性转换；DOCX；A4" in text
    assert "DC_DocumentSubtitle" in {paragraph.style.style_id for paragraph in document.paragraphs}


def test_renderer_converts_raw_html_table_and_styles_caption_and_metadata_labels(tmp_path) -> None:
    markdown = """---
title: AI模型助力提升物资采购质量
---

何宏山

重庆市公共资源交易中心

采购管理部

摘要：本文说明采购质量提升路径。

关键词：采购；质量；模型

表1 选择AI编写工具时应考虑的几个因素

<table><tr><td>序号</td><td>因素</td><td>描述</td></tr><tr><td>1</td><td>功能性</td><td>工具是否具备自动生成模板、智能检查等功能</td></tr></table>

# 一、正文

正文内容。
"""
    output_path = tmp_path / "metadata-table.docx"

    render_docx(
        markdown=markdown,
        style_pack=create_style_pack(name="元数据表格测试", format_id="docx"),
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    document = Document(output_path)
    assert len(document.tables) == 1
    table = document.tables[0]
    assert table.cell(0, 0).text == "序号"
    assert table.cell(1, 2).text == "工具是否具备自动生成模板、智能检查等功能"
    caption = next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("表1"))
    assert caption.style.style_id == "DC_TableCaption"
    assert {paragraph.style.style_id for paragraph in document.paragraphs} >= {
        "DC_DocumentTitle",
        "DC_Author",
        "DC_OrganizationDepartment",
        "DC_AbstractContent",
        "DC_KeywordsContent",
    }
    assert any(run.style and run.style.style_id == "DC_AbstractLabel" for paragraph in document.paragraphs for run in paragraph.runs)
    assert any(run.style and run.style.style_id == "DC_KeywordsLabel" for paragraph in document.paragraphs for run in paragraph.runs)
    assert any(paragraph.style.style_id == "DC_AbstractContent" for paragraph in document.paragraphs)
    assert any(paragraph.style.style_id == "DC_KeywordsContent" for paragraph in document.paragraphs)
    assert document.styles["DC_AbstractLabel"].type == 2  # character style
    assert document.styles["DC_AbstractContent"].type == 1  # paragraph style
    assert document.styles["DC_AbstractLabel"].font.name == "Times New Roman"
    assert document.styles["DC_AbstractContent"].font.name == "Times New Roman"
    assert {
        paragraph.style.style_id
        for row in table.rows
        for cell in row.cells
        for paragraph in cell.paragraphs
    } == {"DC_TableBody"}


def test_renderer_prefers_bundled_pandoc_when_available(tmp_path) -> None:
    bundled_root = tmp_path / "pandoc"
    bundled_root.mkdir()
    bundled_executable = bundled_root / "pandoc.exe"
    bundled_executable.write_bytes(b"not-executed-in-this-test")

    assert resolve_pandoc(bundled_root=bundled_root) == bundled_executable


def test_renderer_writes_self_contained_dc_styles_metadata_and_plain_numbering(tmp_path) -> None:
    markdown = """---
schema: normalized-md/v1
title: 项目建设方案
subtitle: 实施说明
organization: XX公司
department: XX部门
authors:
  - 张三
  - 李四
date: 2026-09-18
abstract: 在安全、制度和生态四个方面推进智慧交易。
keywords:
  - 人工智能
  - 大模型
  - 公共资源交易
  - 数智化
---

# 一、建设背景

## 二、工作内容

正文包含 **重点内容**。

1. 第一项
2. 第二项

| 项目 | 数量 |
| --- | ---: |
| A | 10 |
"""
    output_path = tmp_path / "项目建设方案.docx"

    render_docx(
        markdown=markdown,
        style_pack=create_style_pack(name="测试样式", format_id="docx"),
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    document = Document(output_path)
    style_ids = {paragraph.style.style_id for paragraph in document.paragraphs}
    assert {
        "DC_DocumentTitle",
        "DC_DocumentSubtitle",
        "DC_OrganizationDepartment",
        "DC_Author",
        "DC_Date",
        "DC_AbstractContent",
        "DC_KeywordsContent",
    } <= style_ids
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "摘要：在安全、制度和生态四个方面推进智慧交易。" in text
    assert "关键词：人工智能；大模型；公共资源交易；数智化" in text
    assert round(document.sections[0].page_width.mm) == 210
    assert round(document.sections[0].page_height.mm) == 297
    assert {"DC_Heading1", "DC_Heading2"} <= style_ids
    assert next(paragraph for paragraph in document.paragraphs if paragraph.text == "一、建设背景").style.style_id == "DC_Heading1"
    assert next(paragraph for paragraph in document.paragraphs if paragraph.text == "二、工作内容").style.style_id == "DC_Heading2"
    table_style_ids = {
        paragraph.style.style_id
        for table in document.tables
        for row in table.rows
        for cell in row.cells
        for paragraph in cell.paragraphs
    }
    assert "DC_TableBody" in table_style_ids
    assert all(paragraph.style.style_id != "Heading 2" for paragraph in document.paragraphs)
    assert "1. 第一项" in "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert all(paragraph._p.pPr is None or paragraph._p.pPr.numPr is None for paragraph in document.paragraphs)
    assert any(run.style and run.style.style_id == "DC_Point" for paragraph in document.paragraphs for run in paragraph.runs)

    with zipfile.ZipFile(output_path) as archive:
        styles_xml = archive.read("word/styles.xml").decode("utf-8")
        document_xml = archive.read("word/document.xml").decode("utf-8")
    for style_id in (
        "DC_DocumentTitle",
        "DC_DocumentSubtitle",
        "DC_OrganizationDepartment",
        "DC_Author",
        "DC_Date",
        "DC_AbstractLabel",
        "DC_AbstractContent",
        "DC_KeywordsLabel",
        "DC_KeywordsContent",
        "DC_Heading1",
        "DC_Heading2",
        "DC_Heading3",
        "DC_Heading4",
        "DC_Heading5",
        "DC_Heading6",
        "DC_BodyParagraph",
        "DC_TableBody",
        "DC_Point",
        "DC_ReferenceHeading",
        "DC_ReferenceEntry",
        "DC_Footer",
    ):
        assert f'w:styleId="{style_id}"' in styles_xml
    assert 'w:eastAsia="仿宋"' in styles_xml
    assert 'w:ascii="Times New Roman"' in styles_xml
    assert 'w:val="DC_Point"' in document_xml
    for level in range(1, 7):
        style = document.styles[f"DC_Heading{level}"]
        ppr = style._element.find(qn("w:pPr"))
        assert ppr is not None
        outline = ppr.find(qn("w:outlineLvl"))
        assert outline is not None
        assert outline.get(qn("w:val")) == str(level - 1)


@pytest.mark.parametrize(
    "value",
    ["参考文献：", "（一）参考文献", "（1）参考文献", "参考文献（References）"],
)
def test_reference_heading_variants_are_recognized(value: str) -> None:
    assert _REFERENCE_HEADING_PATTERN.fullmatch(value) is not None


def test_renderer_starts_post_document_styles_only_at_reference_heading(tmp_path) -> None:
    markdown = """# 正文标题

正文段落。

六、参考文献

[1] 参考资料条目。
"""
    output_path = tmp_path / "references.docx"

    render_docx(
        markdown=markdown,
        style_pack=create_style_pack(name="参考文献测试", format_id="docx"),
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    document = Document(output_path)
    paragraphs = {paragraph.text: paragraph.style.style_id for paragraph in document.paragraphs}
    assert paragraphs["正文段落。"] == "DC_BodyParagraph"
    assert paragraphs["六、参考文献"] == "DC_ReferenceHeading"
    assert paragraphs["[1] 参考资料条目。"] == "DC_ReferenceEntry"


def test_renderer_without_reference_heading_has_no_post_document_body_style(tmp_path) -> None:
    output_path = tmp_path / "no-references.docx"
    render_docx(
        markdown="# 正文标题\n\n普通正文。\n",
        style_pack=create_style_pack(name="无参考文献测试", format_id="docx"),
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    document = Document(output_path)
    assert all(
        paragraph.style.style_id not in {"DC_ReferenceHeading", "DC_ReferenceEntry"}
        for paragraph in document.paragraphs
    )


def test_renderer_keeps_selected_chinese_and_western_fonts_in_ooxml(tmp_path) -> None:
    pack = create_style_pack(name="黑体测试", format_id="docx")
    roles = {key: dict(value) for key, value in pack.roles.items()}
    roles["body-paragraph"] = {
        **roles["body-paragraph"],
        "font": {**roles["body-paragraph"]["font"], "chinese_font": "黑体", "western_font": "黑体"},
    }
    pack = pack.model_copy(update={"roles": roles})

    output_path = tmp_path / "font.docx"
    render_docx(
        markdown="正文内容。",
        style_pack=pack,
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    with zipfile.ZipFile(output_path) as archive:
        styles_xml = archive.read("word/styles.xml").decode("utf-8")
    assert 'w:styleId="DC_BodyParagraph"' in styles_xml
    body_style = styles_xml[styles_xml.index('w:styleId="DC_BodyParagraph"') :]
    assert 'w:eastAsia="黑体"' in body_style
    assert 'w:ascii="黑体"' in body_style
    assert 'w:hAnsi="黑体"' in body_style
    assert 'w:cs="黑体"' in body_style


@pytest.mark.parametrize(
    ("rule", "expected_line", "expected_rule"),
    [
        ("maximum", "580", "auto"),
        ("minimum", "580", "atLeast"),
        ("exact", "580", "exact"),
        ("multiple", "360", "auto"),
    ],
)
def test_renderer_writes_line_spacing_rule_and_value_to_ooxml(tmp_path, rule, expected_line, expected_rule) -> None:
    base = create_style_pack(name="行距测试", format_id="docx")
    roles = {key: dict(value) for key, value in base.roles.items()}
    roles["body-paragraph"] = {
        **roles["body-paragraph"],
        "paragraph": {
            **roles["body-paragraph"]["paragraph"],
            "line_spacing_rule": rule,
            "line_spacing_multiple": 1.5 if rule == "multiple" else None,
        },
    }
    pack = base.model_copy(update={"roles": roles})
    output_path = tmp_path / "line-spacing.docx"

    render_docx(
        markdown="正文内容。",
        style_pack=pack,
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    with zipfile.ZipFile(output_path) as archive:
        styles_xml = archive.read("word/styles.xml").decode("utf-8")
    body_style = styles_xml[styles_xml.index('w:styleId="DC_BodyParagraph"') :]
    assert f'w:line="{expected_line}"' in body_style
    assert f'w:lineRule="{expected_rule}"' in body_style


def test_renderer_writes_character_indent_attributes_to_ooxml(tmp_path) -> None:
    base = create_style_pack(name="字符缩进测试", format_id="docx")
    roles = {key: dict(value) for key, value in base.roles.items()}
    roles["body-paragraph"] = {
        **roles["body-paragraph"],
        "paragraph": {
            **roles["body-paragraph"]["paragraph"],
            "first_line_indent_pt": 32,
            "first_line_indent_unit": "character",
            "left_indent_pt": 16,
            "left_indent_unit": "character",
        },
    }
    pack = base.model_copy(update={"roles": roles})
    output_path = tmp_path / "character-indent.docx"

    render_docx(
        markdown="正文内容。",
        style_pack=pack,
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    with zipfile.ZipFile(output_path) as archive:
        styles_xml = archive.read("word/styles.xml").decode("utf-8")
    body_style = styles_xml[styles_xml.index('w:styleId="DC_BodyParagraph"') :]
    assert 'w:firstLineChars="200"' in body_style
    assert 'w:leftChars="100"' in body_style
    assert 'w:firstLine="640"' not in body_style
    assert 'w:left="320"' not in body_style
