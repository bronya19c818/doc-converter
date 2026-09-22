from __future__ import annotations

from typing import Any

from doc_converter.docx_direct.classifier import classify_document
from doc_converter.docx_direct.model import DocumentAnalysis, ElementAnalysis


def _element(
    text: str,
    order: int,
    *,
    style_id: str = "Normal",
    style_name: str = "Normal",
    effective_format: dict[str, Any] | None = None,
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
    )


def test_regions_transition_from_preface_to_body_and_postface() -> None:
    elements = [
        _element(
            "标题",
            0,
            effective_format={
                "alignment": "center",
                "dominant_font_size_pt": 22,
                "dominant_font_size_ratio": 1.0,
            },
        ),
        _element(
            "副标题",
            1,
            effective_format={
                "alignment": "center",
                "dominant_font_size_pt": 16,
                "dominant_font_size_ratio": 1.0,
            },
        ),
        _element("作者：张三", 2),
        _element("摘要：摘要内容", 3),
        _element(
            "2 适用范围",
            4,
            effective_format={
                "outline_level": 0,
                "dominant_font_size_pt": 16,
                "dominant_font_size_ratio": 1.0,
            },
        ),
        _element("正文内容。", 5),
        _element("参考文献", 6),
        _element("[1] 参考资料条目", 7),
    ]

    result = classify_document(DocumentAnalysis(source_sha256="c" * 64, elements=elements))
    by_text = {item.text: item for item in result.elements}

    assert by_text["标题"].region == "preface"
    assert by_text["副标题"].region == "preface"
    assert by_text["2 适用范围"].region == "body"
    assert by_text["正文内容。"].region == "body"
    assert by_text["参考文献"].region == "postface"
    assert by_text["[1] 参考资料条目"].region == "postface"
    assert by_text["标题"].text != by_text["副标题"].text
