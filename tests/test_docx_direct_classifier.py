from __future__ import annotations

from pathlib import Path
from typing import Any

from doc_converter.docx_direct.analyzer import analyze_docx
from doc_converter.docx_direct.classifier import (
    action_for_confidence,
    classify_document,
)
from doc_converter.docx_direct.model import DocumentAnalysis, ElementAnalysis

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


def _synthetic_element(
    text: str,
    order: int,
    *,
    style_id: str = "Normal",
    style_name: str = "Normal",
    effective_format: dict[str, Any] | None = None,
    signals: dict[str, Any] | None = None,
    table_context: dict[str, Any] | None = None,
    numbering_properties: dict[str, Any] | None = None,
) -> ElementAnalysis:
    return ElementAnalysis(
        element_id=f"p-{order + 1:04d}",
        element_type="paragraph",
        text=text,
        document_order=order,
        xml_path=(order,),
        region="body",
        original_style_id=style_id,
        original_style_name=style_name,
        effective_format=effective_format or {},
        signals=signals or {},
        numbering_properties=numbering_properties or {},
        table_context=table_context,
    )


def _classify_synthetic(elements: list[ElementAnalysis]) -> dict[str, ElementAnalysis]:
    analysis = DocumentAnalysis(source_sha256="a" * 64, elements=elements)
    result = classify_document(analysis)
    return {element.text: element for element in result.elements}


def test_outline_level_is_strong_but_not_absolute() -> None:
    by_text = _classify_synthetic(
        [
            _synthetic_element(
                "2 适用范围",
                0,
                effective_format={
                    "outline_level": 0,
                    "alignment": "left",
                    "dominant_font_size_pt": 16,
                    "dominant_font_size_ratio": 1.0,
                },
            ),
            _synthetic_element(
                "表格中的普通正文",
                1,
                effective_format={
                    "outline_level": 0,
                    "dominant_font_size_pt": 12,
                    "dominant_font_size_ratio": 1.0,
                },
                table_context={"table_depth": 1, "row": 0, "column": 0},
            ),
            _synthetic_element(
                "这是一个很长的正文句子，包含完整说明并以句号结束。",
                2,
                effective_format={
                    "outline_level": 0,
                    "dominant_font_size_pt": 12,
                    "dominant_font_size_ratio": 1.0,
                },
            ),
        ]
    )

    assert by_text["2 适用范围"].role == "heading-1"
    assert by_text["表格中的普通正文"].role == "body-table"
    assert by_text["这是一个很长的正文句子，包含完整说明并以句号结束。"].role == "body-paragraph"


def test_custom_style_based_on_heading_is_not_automatically_a_heading() -> None:
    item = _classify_synthetic(
        [
            _synthetic_element(
                "自定义样式正文句。",
                0,
                style_id="CustomHeading",
                style_name="自定义标题",
                effective_format={
                    "outline_level": 0,
                    "dominant_font_size_pt": 16,
                    "dominant_font_size_ratio": 1.0,
                },
                signals={
                    "style_chain": ["Heading1", "CustomHeading"],
                    "based_on_heading": True,
                },
            )
        ]
    )["自定义样式正文句。"]

    assert item.role == "body-paragraph"
    assert item.action == "mapped"
    assert item.signals["based_on_heading"] is True


def test_title_and_subtitle_use_effective_format_and_keep_boundaries() -> None:
    by_text = _classify_synthetic(
        [
            _synthetic_element(
                "有效格式文档标题",
                0,
                effective_format={
                    "alignment": "center",
                    "dominant_font_size_pt": 22,
                    "dominant_font_size_ratio": 1.0,
                },
            ),
            _synthetic_element(
                "有效格式文档副标题",
                1,
                effective_format={
                    "alignment": "center",
                    "dominant_font_size_pt": 16,
                    "dominant_font_size_ratio": 1.0,
                },
            ),
            _synthetic_element("1. 正文起始标题", 2, style_id="Heading1", style_name="Heading 1"),
        ]
    )

    assert by_text["有效格式文档标题"].role == "document-title"
    assert by_text["有效格式文档副标题"].role == "document-subtitle"
    assert by_text["有效格式文档标题"].document_order + 1 == by_text["有效格式文档副标题"].document_order
