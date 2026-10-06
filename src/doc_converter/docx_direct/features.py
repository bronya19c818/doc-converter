"""Objective paragraph features and character-weighted document baselines.

This module never assigns a semantic role. Region values start neutral and are
refined by the context resolver on the shadow copy only.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from doc_converter.docx_direct.model import DocumentAnalysis, ElementAnalysis

HEADING_STYLE = re.compile(r"^(?:heading\s*|标题\s*)([1-6])$", re.I)
AUTHOR_LABEL = re.compile(r"^(?:作者|编制|编写)\s*[:：]\s*\S.{0,39}$")
ORGANIZATION_LABEL = re.compile(r"^(?:单位|部门|编制单位)\s*[:：]\s*\S.{0,79}$")
DATE_PATTERN = re.compile(
    r"^(?:(?:日期|时间)\s*[:：]\s*)?(?:\d{4}年\d{1,2}月(?:\d{1,2}日?)?"
    r"|\d{4}[-./]\d{1,2}[-./]\d{1,2}"
    r"|[二〇零一二三四五六七八九十百]+年[一二三四五六七八九十百]+月)$"
)
CAPTION_PATTERN = re.compile(r"^(表|图|Table|Figure)\s*[一二三四五六七八九十百\d]+", re.I)
ORGANIZATION_PATTERN = re.compile(r"(?:公司|部门|中心|研究院|大学|学院|公司.{0,12}[部处])$")
PERSON_PATTERN = re.compile(r"^[赵钱孙李周吴郑王冯陈卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜谢苏潘葛彭鲁韦马方俞任袁柳][\u4e00-\u9fff]{1,3}$")
REFERENCE_BOUNDARIES = {"参考文献", "参考资料", "references"}
TERMINAL_PUNCTUATION = "。；：，、？！.!?,;:"
NUMBERING_PATTERNS = (
    ("CHAPTER", re.compile(r"^第\s*[一二三四五六七八九十百\d]+\s*章")),
    ("CN_ENUM", re.compile(r"^[一二三四五六七八九十百]+、")),
    ("CN_BRACKET", re.compile(r"^[（(][一二三四五六七八九十百]+[）)]")),
    ("DECIMAL", re.compile(r"^\d+(?:\.\d+)+(?=\s|[^\d.])")),
    ("ARABIC_ENUM", re.compile(r"^\d+[.、](?=\s|[^\d.])|^\d+\s+")),
    ("ARABIC_BRACKET", re.compile(r"^[（(]\d+[）)]")),
    ("CIRCLED", re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]")),
)


def _native_heading(element: ElementAnalysis) -> int | None:
    for value in (element.original_style_id, element.original_style_name):
        match = HEADING_STYLE.fullmatch(value or "")
        if match:
            return int(match.group(1))
    return None


def _numbering(text: str) -> tuple[str | None, int | None, str | None]:
    for family, pattern in NUMBERING_PATTERNS:
        match = pattern.match(text)
        if match:
            token = match.group().strip()
            depth = token.count(".") + 1 if family == "DECIMAL" else None
            return family, depth, token
    return None, None, None


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return None


def _plain_features(element: ElementAnalysis, index: int, total: int) -> dict[str, Any]:
    text = element.text.strip()
    effective = element.effective_format
    family, depth, token = _numbering(text)
    caption = CAPTION_PATTERN.match(text)
    native = _native_heading(element)
    title_style = next((value.lower() for value in (
        element.original_style_id, element.original_style_name,
    ) if value and value.lower() in {"title", "subtitle"}), None)
    size = _number(effective.get("dominant_font_size_pt")) or _number(effective.get("font_size_pt"))
    automatic = element.numbering_properties.get("num_id") not in (None, "0", 0)
    is_list = automatic or (element.original_style_name or "").lower().startswith("list ")
    terminal = bool(text and text[-1] in TERMINAL_PUNCTUATION)
    return {
        "text_length": len(text),
        "has_sentence_punctuation": bool(re.search(r"[。；？！.!?;]", text)),
        "has_terminal_punctuation": terminal,
        "explicit_author_label": bool(AUTHOR_LABEL.fullmatch(text)),
        "explicit_organization_label": bool(ORGANIZATION_LABEL.fullmatch(text)),
        "explicit_date": bool(DATE_PATTERN.fullmatch(text)),
        "person_name_pattern": bool(PERSON_PATTERN.fullmatch(text)),
        "organization_pattern": len(text) <= 80 and bool(ORGANIZATION_PATTERN.search(text)),
        "caption_pattern": caption.group(1).lower() if caption else None,
        "reference_boundary": text.lower().rstrip(":：") in REFERENCE_BOUNDARIES,
        "reference_entry_pattern": bool(re.match(r"^\[\d+\]\s*\S", text)),
        "numbering_family": family,
        "numbering_depth": depth,
        "literal_numbering": token,
        "automatic_numbering": automatic,
        "original_style_id": element.original_style_id,
        "original_style_name": element.original_style_name,
        "native_heading_level": native,
        "native_title_style": title_style,
        "outline_level": effective.get("outline_level"),
        "based_on_heading": bool(element.signals.get("based_on_heading")),
        "table_context": element.table_context,
        "list": is_list,
        "numPr": dict(element.numbering_properties),
        "alignment": effective.get("alignment"),
        "dominant_font_size_pt": size,
        "dominant_font_size_ratio": effective.get("dominant_font_size_ratio"),
        "max_font_size_pt": effective.get("max_font_size_pt"),
        "dominant_bold": effective.get("dominant_bold"),
        "font_name": effective.get("font_name"),
        "keep_next": effective.get("keep_next"),
        "page_break_before": effective.get("page_break_before"),
        "document_order": element.document_order,
        "relative_position": index / max(total - 1, 1),
        "region": "body",
        "is_preface": False,
        "is_body": True,
        "is_postface": False,
        "has_hyperlink": element.has_hyperlink,
        "has_field": element.has_field,
        "has_drawing": element.has_drawing,
        "has_tab": element.has_tab,
        "has_manual_break": element.has_manual_break,
        "short_text": 0 < len(text) <= 80,
        "body_sentence": terminal and len(text) >= 6,
        "custom_style": bool(element.original_style_name)
        and (element.original_style_name or "").lower() not in {"normal", "正文", "body text", "body text 2"}
        and native is None and not is_list,
    }


def extract_document_features(
    analysis: DocumentAnalysis,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return detached facts and baselines without mutating analyzer evidence."""

    features = [_plain_features(e, i, len(analysis.elements)) for i, e in enumerate(analysis.elements)]
    ordinary = [
        f for f in features
        if f["text_length"] and f["table_context"] is None and not f["list"]
        and not f["native_heading_level"] and not f["based_on_heading"]
        and not any(f[k] for k in ("explicit_author_label", "explicit_organization_label", "explicit_date", "caption_pattern", "reference_boundary"))
        and f["body_sentence"]
    ]
    if not ordinary:
        ordinary = [f for f in features if f["text_length"] and f["table_context"] is None
                    and not f["native_heading_level"] and not f["list"]
                    and f["alignment"] != "center" and not f["numbering_family"]]
    distribution: Counter[float] = Counter()
    all_sizes: Counter[float] = Counter()
    styles: Counter[str] = Counter()
    alignments: Counter[str] = Counter()
    for f in features:
        if f["dominant_font_size_pt"] and f["text_length"]:
            all_sizes[f["dominant_font_size_pt"]] += f["text_length"]
    for f in ordinary:
        weight = f["text_length"]
        if f["dominant_font_size_pt"]:
            distribution[f["dominant_font_size_pt"]] += weight
        styles[f["original_style_id"] or "Normal"] += weight
        if f["alignment"]:
            alignments[f["alignment"]] += weight
    body_size = max(distribution, key=lambda s: (distribution[s], -s)) if distribution else None
    leading_sizes = [f["dominant_font_size_pt"] for f in features[:12]
                     if f["dominant_font_size_pt"] and f["table_context"] is None
                     and not f["native_heading_level"] and not f["numbering_family"]
                     and not f["body_sentence"]]
    baseline = {
        "dominant_body_font_size": body_size,
        "font_size_distribution": {str(s): w for s, w in sorted(all_sizes.items())},
        "body_font_size_distribution": {str(s): w for s, w in sorted(distribution.items())},
        "largest_preface_font_size": max(leading_sizes, default=None),
        "common_body_style": styles.most_common(1)[0][0] if styles else None,
        "common_body_alignment": alignments.most_common(1)[0][0] if alignments else None,
        "body_baseline_paragraphs": len(ordinary),
    }
    for f in features:
        size = f["dominant_font_size_pt"]
        f["font_size_to_body_ratio"] = size / body_size if size and body_size else None
        f["largest_preface_size"] = bool(size and size == baseline["largest_preface_font_size"])
        f["common_body_style"] = bool(baseline["common_body_style"]
                                       and (f["original_style_id"] or "Normal") == baseline["common_body_style"])
        f["common_body_alignment"] = bool(baseline["common_body_alignment"]
                                           and f["alignment"] == baseline["common_body_alignment"])
    return features, baseline
