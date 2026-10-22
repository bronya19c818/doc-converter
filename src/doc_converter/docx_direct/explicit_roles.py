"""Narrow source-evidence interfaces, independent of scoring and heading inference."""

import re

from doc_converter.captions import caption_role
from doc_converter.docx_direct.model import ClassificationDecision, ElementAnalysis, InlineSegment

_LABEL = re.compile(r"^\s*(摘要|关键词)\s*[:：]")
_LABEL_ONLY = re.compile(r"^\s*(摘要|关键词)\s*$")


def select_explicit_role(element: ElementAnalysis) -> None:
    role = None
    reason = None
    if element.table_context:
        if element.table_context.get("explicit_header") and element.text.strip():
            role = "table-column-header"
            reason = "最近表格行有显式 w:tblHeader，非首行猜测"
    else:
        match = _LABEL.match(element.text) or _LABEL_ONLY.fullmatch(element.text)
        if match:
            prefix = "abstract" if match.group(1) == "摘要" else "keywords"
            role = prefix + "-label"
            reason = "明确中文摘要/关键词标签"
            element.inline_segments = [InlineSegment(start=0, end=match.end(), role=role)]
            if match.end() < len(element.text):
                element.inline_segments.append(InlineSegment(
                    start=match.end(), end=len(element.text), role=prefix + "-content",
                ))
    context = element.table_context or {}
    if (not element.features.get("list") and not element.numbering_properties.get("num_id")
            and context.get("vertical_merge") != "continue"
            and not any((element.has_field, element.has_drawing, element.has_embedded_object,
                         element.has_math, element.has_manual_break))):
        caption = caption_role(element.text)
        if caption:
            role = caption
            reason = "明确图表标题或制图人/制表人标签，同段时间沿用署名样式"
    if role:
        element.selected_decision = ClassificationDecision(
            role=role, confidence=1, action="mapped", reasons=[reason or role],
        )
        element.selection_source = "explicit"
        element.selection_reason = reason
