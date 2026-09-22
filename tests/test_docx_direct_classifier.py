from __future__ import annotations

from pathlib import Path

from doc_converter.docx_direct.analyzer import analyze_docx
from doc_converter.docx_direct.classifier import (
    action_for_confidence,
    classify_document,
)

FIXTURE = Path(__file__).parent / "fixtures" / "DOCX转Markdown压力测试_V1_结构兼容性.docx"


def _classified() -> dict[str, object]:
    analysis = classify_document(analyze_docx(FIXTURE))
    return {item.text: item for item in analysis.elements if item.text}


def test_classifier_maps_native_headings_and_keeps_lists_preserved() -> None:
    by_text = _classified()

    assert by_text["CASE-H-001 标题层级与正文结构"].role == "heading-1"
    assert by_text["CASE-H2-002 Heading 2 中文标题"].role == "heading-2"
    assert by_text["CASE-H6-006 Heading 6 中文标题"].role == "heading-6"
    assert by_text["CASE-LIST-B1 一级项目符号 A"].role == "unknown"
    assert by_text["CASE-LIST-B1 一级项目符号 A"].action == "preserved"
    assert "列表" in "".join(by_text["CASE-LIST-B1 一级项目符号 A"].reasons)


def test_classifier_recognizes_numbered_heading_but_not_numbered_sentence() -> None:
    by_text = _classified()

    assert by_text["一、一级中文编号但使用普通正文样式 〔CASE-MANUAL-001〕"].role == "heading-1"
    assert by_text["（一）二级中文编号但使用普通正文样式 〔CASE-MANUAL-002〕"].role == "heading-2"
    assert by_text["1. 数字编号标题但使用普通正文样式 〔CASE-MANUAL-003〕"].role == "heading-3"
    literal = by_text["CASE-LIST-LITERAL-001 1. 这行看起来像编号，但只是普通正文中的字面文本。"]
    assert literal.role == "unknown"
    assert literal.action == "preserved"


def test_classifier_keeps_title_and_subtitle_as_separate_elements() -> None:
    by_text = _classified()
    roles = [
        (text, element.role)
        for text, element in by_text.items()
        if element.role in {"document-title", "document-subtitle"}
    ]
    assert roles[:2] == [
        ("DOCX → Markdown 转换压力测试文档", "document-title"),
        ("V1 · 结构兼容性 / 边界场景 / 可定位验收", "document-subtitle"),
    ]


def test_classifier_maps_body_table_and_caption_roles() -> None:
    by_text = _classified()

    assert by_text["本章验证 Word 内置 Heading 1–6 与普通正文在 Markdown 中是否映射为正确层级。"].role == "body-paragraph"
    assert by_text["编号"].role == "body-table"
    assert by_text["表1 规则表格：应尽量转换成 Markdown pipe table。"].role == "table-caption"
    assert by_text["图1 CASE-IMG-CAPTION-001 文档转换处理流程示意图"].role == "figure-caption"


def test_action_thresholds_are_deterministic() -> None:
    assert action_for_confidence("heading-1", 0.90) == "mapped"
    assert action_for_confidence("heading-1", 0.89) == "uncertain"
    assert action_for_confidence("heading-1", 0.70) == "uncertain"
    assert action_for_confidence("heading-1", 0.69) == "preserved"
    assert action_for_confidence("unknown", 0.99) == "preserved"
