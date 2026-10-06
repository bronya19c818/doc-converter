"""Deterministic, conservative semantic classification for DOCX paragraphs."""

from __future__ import annotations

import re
from typing import Any

from doc_converter.docx_direct.decision_selector import select_decision
from doc_converter.docx_direct.features import extract_document_features
from doc_converter.docx_direct.model import (
    Action,
    ClassificationDecision,
    DecisionMode,
    DocumentAnalysis,
    DocumentRegion,
    ElementAnalysis,
)
from doc_converter.docx_direct.resolver import resolve_candidates
from doc_converter.docx_direct.scoring import ScoringConfig, decide, score_roles

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
_CAPTION_CREDIT_PATTERN = re.compile(
    r"^制(?P<kind>[图表])人\s*[:：][^\r\n]{0,60}?时间\s*[:：][^\r\n]{0,30}$"
)
_AUTHOR_LABEL_PATTERN = re.compile(r"^\s*(作者|编制|编写)\s*[:：]\s*(\S.{0,39})\s*$")
_ORGANIZATION_LABEL_PATTERN = re.compile(
    r"^\s*(单位|部门|编制单位)\s*[:：]\s*(\S.{0,79})\s*$"
)
_DATE_PATTERN = re.compile(
    r"^(?:"
    r"\d{4}年\d{1,2}月(?:\d{1,2}日?)?|"
    r"\d{4}[-.]\d{1,2}[-.]\d{1,2}|"
    r"[二〇零一二三四五六七八九十百]+年[一二三四五六七八九十百]+月"
    r")$"
)
_ORGANIZATION_SUFFIX_PATTERN = re.compile(r"(公司|部门|中心|研究院|大学|学院)$")
_PERSON_NAME_PATTERN = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
_COMMON_SURNAMES = frozenset(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳"
)


def action_for_confidence(role: str, confidence: float) -> Action:
    """Convert a role confidence to the conservative action policy."""

    if role not in SUPPORTED_ROLES:
        return "preserved"
    if confidence >= 0.90:
        return "mapped"
    if confidence >= 0.70:
        return "uncertain"
    return "preserved"


def classify_document(
    analysis: DocumentAnalysis, *, scoring_config: ScoringConfig | None = None,
    decision_mode: DecisionMode = "hybrid",
) -> DocumentAnalysis:
    """Keep legacy evidence and select one independent conversion decision."""

    config = scoring_config or ScoringConfig()
    # Extract from analyzer evidence, never from legacy's role/region decisions.
    features, baselines = extract_document_features(analysis)
    candidates = [score_roles(f, config) for f in features]
    baselines.update(resolve_candidates(features, candidates, config))
    legacy = classify_document_legacy(analysis)
    for element, facts, roles in zip(legacy.elements, features, candidates, strict=True):
        element.features = facts
        element.candidates = roles
        element.legacy_decision = ClassificationDecision(
            role=element.role, confidence=element.confidence, action=element.action,
            reasons=list(element.reasons),
        )
        element.scored_decision = decide(roles, config)
        element.selected_decision, element.selection_source, element.selection_reason = (
            select_decision(element, config, decision_mode)
        )
    return legacy.model_copy(update={
        "classification_mode": decision_mode,
        "document_baselines": baselines,
        "scoring_config": config.model_dump(mode="json"),
    })


def classify_document_legacy(analysis: DocumentAnalysis) -> DocumentAnalysis:
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
        if element.region == "preface":
            metadata = _metadata_decision(element)
            if metadata is not None:
                classified.append(metadata)
                continue
        if _is_heading_style(element.original_style_id, element.original_style_name):
            level = _heading_level(element.original_style_id, element.original_style_name)
            classified.append(_decision(element, f"heading-{level}", 0.99, "使用 Word 原生 Heading 样式"))
            continue
        if _is_list(element):
            classified.append(_decision(element, "unknown", 0.99, "检测到自动列表或项目符号，保留列表语义"))
            continue
        outline_level = _outline_heading_level(element)
        if outline_level is not None:
            classified.append(
                _decision(
                    element,
                    f"heading-{outline_level}",
                    0.97,
                    "outlineLvl 与段落内容共同符合标题特征",
                    signals={"outline_heading": True},
                )
            )
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
        if _is_body_sentence(text):
            classified.append(_decision(element, "body-paragraph", 0.93, "完整正文句特征优先于继承的标题样式属性"))
            continue
        if _is_custom_style(element.original_style_name):
            classified.append(_decision(element, "unknown", 0.85, "自定义或特殊 Word 样式无法安全映射"))
            continue
        classified.append(_decision(element, "body-paragraph", 0.93, "普通非空正文段落"))

    _classify_caption_credits(classified)
    return analysis.model_copy(update={"elements": classified})


def _classify_caption_credits(elements: list[ElementAnalysis]) -> None:
    """Give a caption's adjacent creator/date line the same paragraph role."""

    for index in range(1, len(elements)):
        caption = elements[index - 1]
        credit = elements[index]
        if caption.role not in {"figure-caption", "table-caption"} or caption.action != "mapped":
            continue
        if credit.table_context is not None or credit.numbering_properties.get("num_id"):
            continue
        match = _CAPTION_CREDIT_PATTERN.fullmatch(credit.text.strip())
        if match is None:
            continue
        role = "figure-caption" if match.group("kind") == "图" else "table-caption"
        if caption.role != role:
            continue
        elements[index] = _decision(
            credit,
            role,
            0.98,
            "紧邻图表标题的制图人或制表人及时间说明",
            signals={"caption_credit": True},
        )


def _decision(
    element: ElementAnalysis,
    role: str,
    confidence: float,
    reason: str,
    *,
    signals: dict[str, Any] | None = None,
) -> ElementAnalysis:
    merged_signals = dict(element.signals)
    if signals:
        merged_signals.update(signals)
    return element.model_copy(
        update={
            "role": role,
            "confidence": confidence,
            "action": action_for_confidence(role, confidence),
            "reasons": [reason],
            "signals": merged_signals,
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
        elif (
            _is_heading_style(element.original_style_id, element.original_style_name)
            or _outline_heading_level(element) is not None
            or _numbered_heading_level(text)
        ):
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
    title = _decision(
        title,
        "document-title",
        0.98,
        "文前居中且有效主导字号最大的标题候选",
        signals={"title_candidate": True},
    )
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
            signals={"title_candidate": True},
        )


def _alignment(element: ElementAnalysis) -> str | None:
    alignment = element.effective_format.get("alignment")
    if alignment is None:
        alignment = element.paragraph_properties.get("alignment")
    if not isinstance(alignment, dict):
        return str(alignment) if isinstance(alignment, str) else None
    return _attribute_value(alignment, "val")


def _font_size_pt(element: ElementAnalysis) -> float:
    dominant = element.effective_format.get("dominant_font_size_pt")
    if isinstance(dominant, (int, float)):
        return float(dominant)
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


def _outline_heading_level(element: ElementAnalysis) -> int | None:
    """Return a conservative heading level from outline evidence and context."""

    if element.table_context is not None or _is_list(element):
        return None
    if element.signals.get("based_on_heading"):
        return None
    text = element.text.strip()
    if not text or len(text) > 80 or _is_body_sentence(text):
        return None
    if any(
        bool(element.signals.get(key)) or bool(element.effective_format.get(key))
        for key in ("has_drawing", "has_field", "has_manual_break")
    ):
        return None
    value = element.effective_format.get("outline_level")
    if not isinstance(value, (int, float, str)):
        return None
    try:
        level = int(value)
    except (TypeError, ValueError):
        return None
    if 0 <= level <= 5:
        return level + 1
    return None


def _is_body_sentence(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) >= 6 and stripped.endswith(tuple(_TERMINAL_BODY_PUNCTUATION))


def _metadata_decision(element: ElementAnalysis) -> ElementAnalysis | None:
    text = element.text.strip()
    if _AUTHOR_LABEL_PATTERN.fullmatch(text):
        return _decision(
            element,
            "author",
            0.98,
            "检测到明确的作者或编制标签",
            signals={"metadata_label": "author"},
        )
    if _ORGANIZATION_LABEL_PATTERN.fullmatch(text):
        return _decision(
            element,
            "organization-department",
            0.98,
            "检测到明确的单位或部门标签",
            signals={"metadata_label": "organization-department"},
        )
    if _DATE_PATTERN.fullmatch(text):
        return _decision(
            element,
            "date",
            0.96,
            "文前段落符合明确日期格式",
            signals={"date_pattern": True},
        )
    if _PERSON_NAME_PATTERN.fullmatch(text) and text[0] in _COMMON_SURNAMES:
        return _decision(
            element,
            "author",
            0.68,
            "文前纯姓名缺少明确标签，仅保留为低置信元数据线索",
            signals={"unlabeled_metadata": "author"},
        )
    if _ORGANIZATION_SUFFIX_PATTERN.search(text) and len(text) <= 40:
        return _decision(
            element,
            "organization-department",
            0.72,
            "文前机构名称缺少明确标签，仅保留为低置信元数据线索",
            signals={"unlabeled_metadata": "organization-department"},
        )
    return None


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
    if normalized.startswith(("摘要", "关键词", "作者", "单位", "部门", "日期", "时间")):
        return True
    if _DATE_PATTERN.fullmatch(text.strip()):
        return True
    if _PERSON_NAME_PATTERN.fullmatch(text.strip()) and text.strip()[0] in _COMMON_SURNAMES:
        return True
    return bool(_ORGANIZATION_SUFFIX_PATTERN.search(text.strip()) and len(text.strip()) <= 40)


def _is_reference_boundary(text: str) -> bool:
    return text.strip().lower().rstrip("：:") in {"参考文献", "参考资料", "references"}
