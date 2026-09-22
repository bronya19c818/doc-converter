from __future__ import annotations

from typing import Any

from doc_converter.docx_direct.classifier import classify_document
from doc_converter.docx_direct.model import DocumentAnalysis, ElementAnalysis


def _element(text: str, order: int, *, alignment: str | None = None) -> ElementAnalysis:
    effective_format: dict[str, Any] = {
        "dominant_font_size_pt": 16,
        "dominant_font_size_ratio": 1.0,
    }
    if alignment is not None:
        effective_format["alignment"] = alignment
    return ElementAnalysis(
        element_id=f"p-{order + 1:04d}",
        element_type="paragraph",
        text=text,
        document_order=order,
        xml_path=(order,),
        region="body",
        original_style_id="Normal",
        original_style_name="Normal",
        effective_format=effective_format,
    )


def _classified(elements: list[ElementAnalysis]) -> dict[str, ElementAnalysis]:
    analysis = DocumentAnalysis(source_sha256="b" * 64, elements=elements)
    return {item.text: item for item in classify_document(analysis).elements}


def test_classifier_maps_explicit_preface_metadata_and_keeps_body_date_as_body() -> None:
    by_text = _classified(
        [
            _element("文档标题", 0, alignment="center"),
            _element("作者：张三", 1, alignment="center"),
            _element("单位：国网福建省电力有限公司", 2, alignment="center"),
            _element("2026年9月22日", 3, alignment="center"),
            _element("1. 适用范围", 4),
            _element("2026.09.22 出现在正文中。", 5),
        ]
    )

    assert by_text["作者：张三"].role == "author"
    assert by_text["作者：张三"].action == "mapped"
    assert by_text["单位：国网福建省电力有限公司"].role == "organization-department"
    assert by_text["单位：国网福建省电力有限公司"].action == "mapped"
    assert by_text["2026年9月22日"].role == "date"
    assert by_text["2026年9月22日"].action == "mapped"
    assert by_text["2026.09.22 出现在正文中。"].role == "body-paragraph"


def test_classifier_does_not_force_unlabeled_name_or_organization() -> None:
    by_text = _classified(
        [
            _element("文档标题", 0, alignment="center"),
            _element("张三", 1),
            _element("国网福建省电力有限公司龙岩供电公司", 2),
            _element("1. 正文标题", 3),
        ]
    )

    assert by_text["张三"].action in {"uncertain", "preserved"}
    assert by_text["国网福建省电力有限公司龙岩供电公司"].action in {
        "uncertain",
        "preserved",
    }
    assert by_text["张三"].role != "author" or by_text["张三"].action != "mapped"
    assert (
        by_text["国网福建省电力有限公司龙岩供电公司"].role != "organization-department"
        or by_text["国网福建省电力有限公司龙岩供电公司"].action != "mapped"
    )
