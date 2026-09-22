"""Deterministic, conservative semantic classification for DOCX paragraphs."""

from __future__ import annotations

import re
from typing import Any

from doc_converter.docx_direct.model import (
    Action,
    DocumentAnalysis,
    DocumentRegion,
    ElementAnalysis,
)

SUPPORTED_ROLES = frozenset(
    {
        "document-title",
        "document-subtitle",
        "organization-department",
        "author",
        "date",
        "heading-1",
        "heading-2",
        "heading-3",
        "heading-4",
        "heading-5",
        "heading-6",
        "body-paragraph",
        "body-table",
        "table-caption",
        "figure-caption",
        "reference-heading",
        "reference-entry",
    }
)

_HEADING_STYLE = re.compile(r"^(?:heading\s*|heading)([1-6])$", re.IGNORECASE)
_NUMBERED_PREFIXES = (
    (re.compile(r"^\s*一、"), 1),
    (re.compile(r"^\s*（[一二三四五六七八九十百]+）"), 2),
    (re.compile(r"^\s*（\d+）"), 2),
    (re.compile(r"^\s*第\s*[一二三四五六七八九十百\d]+\s*[章节]"), 1),
    (re.compile(r"^\s*①"), 3),
    (re.compile(r"^\s*〔[^〕]+〕"), 3),
    (re.compile(r"^\s*【[^】]+】"), 3),
    (re.compile(r"^\s*\d+、"), 2),
    (re.compile(r"^\s*\d+(?:\.\d+)+\s+"), 2),
    (re.compile(r"^\s*\d+\.\s+"), 3),
)
_TERMINAL_BODY_PUNCTUATION = "。；：，、？！.!?,;:"
_CAPTION_PATTERN = re.compile(r"^\s*([表图])\s*(?:[一二三四五六七八九十百\d]+)")


def action_for_confidence(role: str, confidence: float) -> Action:
    """Convert a role confidence to the conservative action policy."""

    if role not in SUPPORTED_ROLES:
        return "preserved"
    if confidence >= 0.90:
        return "mapped"
    if confidence >= 0.70:
        return "uncertain"
    return "preserved"


def classify_document(analysis: DocumentAnalysis) -> DocumentAnalysis:
    """Return a classified copy of an analysis without touching the source DOCX."""

    elements = [element.model_copy(deep=True) for element in analysis.elements]
    _assign_regions(elements)
    _classify_title_area(elements)
    reference_started = False

    classified: list[ElementAnalysis] = []
    for element in elements:
        text = element.text.strip()
        if _is_reference_boundary(text):
            reference_started = True
            classified.append(_decision(element, "reference-heading", 0.98, "检测到参考文献边界"))
            continue
        if not text:
            classified.append(_decision(element, "unknown", 0.0, "空段落保留原样"))
            continue
        if element.role in {"document-title", "document-subtitle"}:
            classified.append(element)
            continue
        if reference_started and not element.table_context:
            if _is_list(element):
                classified.append(_decision(element, "unknown", 0.99, "参考文献中的自动列表保留原样"))
            else:
                classified.append(_decision(element, "reference-entry", 0.95, "参考文献边界后的条目"))
            continue
        if _is_heading_style(element.original_style_id, element.original_style_name):
            level = _heading_level(element.original_style_id, element.original_style_name)
            classified.append(_decision(element, f"heading-{level}", 0.99, "使用 Word 原生 Heading 样式"))
            continue
        if _is_list(element):
            classified.append(_decision(element, "unknown", 0.99, "检测到自动列表或项目符号，保留列表语义"))
            continue
        numbered_level = _numbered_heading_level(text)
        if numbered_level is not None:
            classified.append(_decision(element, f"heading-{numbered_level}", 0.94, "独立编号段落符合标题特征"))
            continue
        if element.table_context is not None:
            classified.append(_decision(element, "body-table", 0.95, "表格单元格内普通段落"))
            continue
        caption = _caption_role(text)
        if caption is not None:
            classified.append(_decision(element, caption, 0.96, "检测到独立表题或图题"))
            continue
        if _is_literal_numbering(element.text):
            classified.append(_decision(element, "unknown", 0.96, "疑似正文中的字面编号，避免自动升格"))
            continue
        if _is_custom_style(element.original_style_name):
            classified.append(_decision(element, "unknown", 0.85, "自定义或特殊 Word 样式无法安全映射"))
            continue
        classified.append(_decision(element, "body-paragraph", 0.93, "普通非空正文段落"))

    return analysis.model_copy(update={"elements": classified})


def _decision(element: ElementAnalysis, role: str, confidence: float, reason: str) -> ElementAnalysis:
    return element.model_copy(
        update={
            "role": role,
            "confidence": confidence,
            "action": action_for_confidence(role, confidence),
            "reasons": [reason],
        }
    )


def _assign_regions(elements: list[ElementAnalysis]) -> None:
    body_started = False
    postface_started = False
    for element in elements:
        text = element.text.strip()
        if _is_reference_boundary(text):
            postface_started = True
        if postface_started:
            region: DocumentRegion = "postface"
        elif body_started:
            region = "body"
        elif _is_heading_style(element.original_style_id, element.original_style_name) or _numbered_heading_level(text):
            body_started = True
            region = "body"
        else:
            region = "preface"
        element.region = region


def _classify_title_area(elements: list[ElementAnalysis]) -> None:
    candidates = [
        element
        for element in elements
        if element.region == "preface"
        and element.table_context is None
        and element.text.strip()
        and _alignment(element) == "center"
        and not _metadata_like(element.text)
        and len(element.text.strip()) <= 80
    ]
    if not candidates:
        return
    title = max(candidates, key=lambda item: (_font_size_pt(item), -item.document_order))
    title = _decision(title, "document-title", 0.98, "文前居中且字号最大的标题候选")
    elements[title.document_order] = title
    title_size = _font_size_pt(title)
    subtitle_candidates = [
        item
        for item in candidates
        if item.document_order > title.document_order and _font_size_pt(item) < title_size
    ]
    if subtitle_candidates:
        subtitle = min(subtitle_candidates, key=lambda item: item.document_order)
        elements[subtitle.document_order] = _decision(
            subtitle,
            "document-subtitle",
            0.95,
            "标题后的独立居中副标题",
        )


def _alignment(element: ElementAnalysis) -> str | None:
    alignment = element.paragraph_properties.get("alignment")
    if not isinstance(alignment, dict):
        return None
    return _attribute_value(alignment, "val")


def _font_size_pt(element: ElementAnalysis) -> float:
    sizes: list[float] = []
    for run in element.run_properties:
        if not isinstance(run, dict):
            continue
        size = run.get("size")
        value = _attribute_value(size, "val") if isinstance(size, dict) else None
        if value is not None:
            try:
                sizes.append(float(value) / 2)
            except ValueError:
                continue
    return max(sizes, default=0.0)


def _attribute_value(value: dict[str, Any] | None, attribute: str) -> str | None:
    if not value:
        return None
    for key, item in value.items():
        if key == attribute or key.endswith("}" + attribute):
            return str(item)
    return None


def _heading_level(style_id: str | None, style_name: str | None) -> int:
    for value in (style_id, style_name):
        if not value:
            continue
        match = _HEADING_STYLE.match(value.replace(" ", ""))
        if match:
            return int(match.group(1))
    return 1


def _is_heading_style(style_id: str | None, style_name: str | None) -> bool:
    return any(
        value is not None and _HEADING_STYLE.match(value.replace(" ", ""))
        for value in (style_id, style_name)
    )


def _numbered_heading_level(text: str) -> int | None:
    stripped = text.strip()
    if not stripped or stripped.endswith(tuple(_TERMINAL_BODY_PUNCTUATION)):
        return None
    for pattern, level in _NUMBERED_PREFIXES:
        match = pattern.match(stripped)
        if match and len(stripped[match.end() :].strip()) <= 35:
            return min(level, 6)
    return None


def _is_list(element: ElementAnalysis) -> bool:
    style = (element.original_style_name or "").lower()
    numbering = element.numbering_properties
    return style.startswith("list ") or bool(numbering.get("num_id"))


def _caption_role(text: str) -> str | None:
    match = _CAPTION_PATTERN.match(text)
    if not match:
        return None
    return "table-caption" if match.group(1) == "表" else "figure-caption"


def _is_literal_numbering(text: str) -> bool:
    if text.lstrip().startswith("CASE-LIST-LITERAL"):
        return True
    return bool(re.search(r"\b\d+[.)]\s+", text) and text.rstrip().endswith(tuple(_TERMINAL_BODY_PUNCTUATION)))


def _is_custom_style(style_name: str | None) -> bool:
    if not style_name:
        return False
    normalized = style_name.lower()
    return normalized not in {"normal", "正文", "body text", "body text 2"} and not normalized.startswith(
        ("heading", "list ")
    )


def _metadata_like(text: str) -> bool:
    normalized = text.strip().lower().rstrip("：:")
    return normalized.startswith(("摘要", "关键词", "作者", "单位", "部门", "日期", "时间"))


def _is_reference_boundary(text: str) -> bool:
    return text.strip().lower().rstrip("：:") in {"参考文献", "参考资料", "references"}
