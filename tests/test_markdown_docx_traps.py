"""Regression tests for the defects recorded in the DOCX trap catalogue.

Each case drives the real normalization and rendering pipeline, so a future
change to preprocessing or postprocessing cannot silently reintroduce them.
"""

from __future__ import annotations

import zipfile

from docx import Document

from doc_converter.normalizer import normalize_markdown
from doc_converter.renderer import render_docx
from doc_converter.style_library import create_style_pack


def _convert(tmp_path, name: str, markdown: str) -> tuple[Document, str]:
    normalized = normalize_markdown(markdown, filename=f"{name}.md")
    result = render_docx(
        markdown=normalized.markdown,
        style_pack=create_style_pack(name="陷阱回归", format_id="docx"),
        output_path=tmp_path / name / "out.docx",
        work_dir=tmp_path / name / "work",
        role_decisions=normalized.report["decisions"],
    )
    document = Document(result.output_path)
    with zipfile.ZipFile(result.output_path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return document, xml


def test_page_break_marker_keeps_both_paragraphs_without_a_blank_one(tmp_path) -> None:
    document, xml = _convert(
        tmp_path, "break", "前半。\n\n<!-- doc-converter:page-break -->\n\n后半。\n"
    )

    assert [p.text for p in document.paragraphs] == ["前半。", "后半。"]
    assert 'w:br w:type="page"' in xml


def test_horizontal_rule_does_not_leave_an_empty_paragraph(tmp_path) -> None:
    document, _ = _convert(tmp_path, "rule", "第一段。\n\n---\n\n第二段。\n")

    assert [p.text for p in document.paragraphs] == ["第一段。", "第二段。"]


def test_unterminated_html_comment_does_not_swallow_following_text(tmp_path) -> None:
    document, _ = _convert(
        tmp_path, "comment", "第一段。\n\n<!-- 未闭合注释\n\n第二段。\n"
    )

    assert [p.text for p in document.paragraphs] == ["第一段。", "第二段。"]


def test_inline_code_comment_marker_is_not_treated_as_html_comment(tmp_path) -> None:
    document, _ = _convert(tmp_path, "inline-comment", "正文含 `<!-- 片段` 说明。\n")

    assert "-->" not in document.paragraphs[0].text
    assert "<!--" in document.paragraphs[0].text


def test_table_caption_glued_to_header_still_renders_a_table(tmp_path) -> None:
    document, _ = _convert(
        tmp_path,
        "caption",
        "正文一段。\n\n表1  说明\n| 甲 | 乙 |\n| --- | --- |\n| 1 | 2 |\n\n正文。\n",
    )

    assert len(document.tables) == 1
    assert document.tables[0].cell(1, 1).text == "2"


def test_pipe_inside_table_code_span_keeps_the_cell(tmp_path) -> None:
    document, _ = _convert(
        tmp_path, "pipe", "| 命令 | 说明 |\n| --- | --- |\n| `x|y` | 竖线 |\n"
    )

    assert [cell.text for cell in document.tables[0].rows[1].cells] == ["x|y", "竖线"]


def test_inline_html_emphasis_and_line_break_are_kept(tmp_path) -> None:
    document, _ = _convert(
        tmp_path, "inline", "普通 <strong>粗</strong> 与 <u>下划线</u> 以及 <br> 换行。\n"
    )

    paragraph = document.paragraphs[0]
    assert "粗" in paragraph.text and "下划线" in paragraph.text
    assert "以及" in paragraph.text and "换行" in paragraph.text
    assert any(run.style is not None and run.style.style_id == "DC_Point" and "粗" in run.text
               for run in paragraph.runs)


def test_indented_code_uses_code_block_style_without_heading_promotion(tmp_path) -> None:
    document, _ = _convert(
        tmp_path,
        "code",
        "执行顺序如下：\n\n    # 先跑增量\n    python run.py\n",
    )

    styles = [(p.style.style_id, p.text) for p in document.paragraphs]
    assert styles[0] == ("DC_BodyParagraph", "执行顺序如下：")
    assert styles[1][0] == "DC_CodeBlock"
    assert "# 先跑增量" in styles[1][1]
    assert not any(style.startswith("DC_Heading") for style, _ in styles)


def test_missing_image_caption_is_not_duplicated(tmp_path) -> None:
    document, _ = _convert(
        tmp_path, "image", "![图1  系统架构](images/missing.png)\n\n图1  系统架构\n"
    )

    captions = [p.text for p in document.paragraphs if p.style.style_id == "DC_FigureCaption"]
    assert captions == ["图1 系统架构"]


def test_inline_math_is_not_dropped(tmp_path) -> None:
    _, xml = _convert(tmp_path, "math", "原文。\n\n$x^2+1$\n")

    assert "oMath" in xml


def test_ordered_list_keeps_word_numbering_and_body_style(tmp_path) -> None:
    document, _ = _convert(tmp_path, "list", "## 1.2 问题\n\n1. 甲项。\n2. 乙项。\n")

    items = [p for p in document.paragraphs if p._p.xpath("./w:pPr/w:numPr")]
    assert [item.text for item in items] == ["甲项。", "乙项。"]
    assert all(item.style.style_id == "DC_BodyParagraph" for item in items)