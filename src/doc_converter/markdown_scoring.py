"""Markdown-native evidence, candidate competition and document-wide resolution.

Scores measure heuristic strength, not statistical probability. Source slices
are retained so the executor never reconstructs inline Markdown or lists.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from markdown_it import MarkdownIt

from doc_converter.docx_direct.model import RoleCandidate
from doc_converter.docx_direct.scoring import ScoringConfig, contribute
from doc_converter.markdown_preprocess import (
    _heading_kind,
    _heading_level_for_title,
    _looks_like_bare_heading_text,
    _looks_like_technical_standard,
    _unescape_ordered_heading_marker,
    is_standard_code_line,
)
from doc_converter.normalizer import (
    _infer_title_area_role,
    _is_date_candidate,
    _is_subtitle_candidate,
    _metadata_label_value,
)

_LABEL = re.compile(
    r"^(作者单位|作者|单位|机构|组织|部门|所属部门|日期|时间|发布时间|摘要|关键词)\s*[:：]\s*([\s\S]*)$"
)
_CAPTION = re.compile(r"^(表|图|fig(?:ure)?\.?|table)\s*(?:\d+(?:[.-]\d+)*|[一二三四五六七八九十]+)\s*(?:[：:、.．)）\s]|$)", re.I)
_REFERENCE = re.compile(r"^(?:(?:\d+|[一二三四五六七八九十]+)[、.．)\s]*|[（(](?:\d+|[一二三四五六七八九十]+)[）)]\s*)?(?:参考文献|参考资料|references?)\s*[:：]?$", re.I)
_SENTENCE = re.compile(r"[。；;，,！？!?：:.]$")
_BODY_WORDS = re.compile(r"应当|不得|需要|负责|确保|应按照|应根据|宜采用|由.+组织|按照.+(?:要求|装箱|执行)")
_TITLE_SUFFIX = re.compile(r"方案|报告|研究|计划|标题|规范书|总结|测试|标准$")
_SUBTITLE = re.compile(r"^(?:——|—|--|基于|关于|以.+为)")

METADATA_ROLE_KEYS = {
    "document-title": "title", "document-subtitle": "subtitle",
    "organization": "organization", "department": "department", "author": "authors",
    "date": "date", "abstract-label": "abstract", "keywords-label": "keywords",
}


@dataclass
class MarkdownBlock:
    start: int
    end: int
    kind: str
    text: str
    inline: str
    level: int = 0
    protected: bool = False
    features: dict[str, Any] = field(default_factory=dict)
    candidates: list[RoleCandidate] = field(default_factory=list)
    role: str = "body-paragraph"
    score: float = 0
    margin: float = 0
    confidence_band: str = "low"
    reason: str = ""
    metadata_value: str | None = None


def parse_blocks(lines: list[str]) -> list[MarkdownBlock]:
    """Read parser spans, including nested protection, without round-tripping AST."""
    tokens = MarkdownIt("commonmark", {"html": True}).enable("table").parse("\n".join(lines))
    blocks: list[MarkdownBlock] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.level != 0 or token.map is None or token.nesting == -1:
            index += 1
            continue
        start, end = token.map
        while end > start and not lines[end - 1].strip():
            end -= 1
        kind = token.type.removesuffix("_open")
        level = int(token.tag[1:]) if kind == "heading" else 0
        protected = kind not in {"heading", "paragraph", "ordered_list"}
        if kind == "ordered_list":
            following = index + 1
            items = 0
            nested = False
            while following < len(tokens) and tokens[following].level > 0:
                child = tokens[following]
                items += int(child.type == "list_item_open" and child.level == 1)
                nested |= child.type in {"bullet_list_open", "ordered_list_open", "fence", "code_block", "blockquote_open"}
                following += 1
            # A singleton can be an exporter-flattened heading, but only after
            # contextual scoring. Multiple/nested/continuation items are lists.
            protected = items != 1 or nested or end - start > 1
        inline = "\n".join(lines[start:end])
        if kind == "heading":
            inline_token = tokens[index + 1]
            inline = inline_token.content
        spans = [(start, end, inline)]
        if kind == "paragraph" and not protected and end - start > 1:
            cuts = [start] + [i for i in range(start + 1, end) if _LABEL.match(lines[i].strip()) or lines[i].strip() in {"摘要", "关键词"} or lines[i - 1].strip() in {"摘要", "关键词"}]
            if len(cuts) > 1:
                boundaries = cuts + [end]
                spans = [(left, right, "\n".join(lines[left:right])) for left, right in zip(boundaries, boundaries[1:])]
        for left, right, raw_inline in spans:
            text_tokens = MarkdownIt().parseInline(raw_inline)
            inline_children = text_tokens[0].children or []
            plain = "".join(child.content if child.type != "softbreak" else "\n" for child in inline_children if child.type in {"text", "code_inline", "image", "softbreak"})
            is_protected = protected or any(re.match(r"^\s*\[\^[^]]+\]:|^\s*\[[^]]+\]:", line) for line in lines[left:right])
            blocks.append(MarkdownBlock(left, right, kind, plain.strip(), raw_inline, level, is_protected))
        index += 1
    return blocks


def analyze_markdown(
    lines: list[str], metadata: dict[str, Any], line_map: list[int],
    config: ScoringConfig | None = None,
) -> tuple[list[MarkdownBlock], dict[str, Any]]:
    """Resolve roles from parser evidence, explicit anchors and whole-document families."""
    config = config or ScoringConfig()
    blocks = parse_blocks(lines)
    standard = _looks_like_technical_standard("\n".join(lines))
    for block in blocks:
        title = _unescape_ordered_heading_marker(block.inline).strip()
        family = _heading_kind(title, standard_document=standard)
        block.features = {
            "parser_kind": block.kind, "explicit_level": block.level, "render_text": block.text,
            "numbering_family": family, "short_text": len(block.text) <= 80,
            "terminal_punctuation": bool(_SENTENCE.search(block.text)),
            "body_sentence": bool(_SENTENCE.search(block.text) or _BODY_WORDS.search(block.text)),
            "protected": block.protected, "source_line": line_map[block.start],
        }
    families = Counter(
        b.features["numbering_family"] for b in blocks
        if not b.protected and b.features["numbering_family"] and not b.features["body_sentence"]
    )
    # Correct, explicitly varied Markdown hierarchy outranks number inference.
    numbered_explicit = [b for b in blocks if b.level and b.features["numbering_family"]]
    levels = {b.level for b in numbered_explicit}
    preserve_explicit = len(levels) > 1
    anchors: dict[str, int] = {}
    grouped: dict[str, list[int]] = defaultdict(list)
    if preserve_explicit:
        for b in numbered_explicit:
            grouped[b.features["numbering_family"]].append(b.level)
        anchors = {f: Counter(values).most_common(1)[0][0] for f, values in grouped.items()}

    decimal_offsets = []
    for block in numbered_explicit:
        if block.features["numbering_family"] == "decimal":
            match = re.match(r"\d+(?:\s*\.\s*\d+)+", block.inline)
            if match:
                decimal_offsets.append(block.level - match.group().count(".") - 1)
    decimal_offset = Counter(decimal_offsets).most_common(1)[0][0] if decimal_offsets and preserve_explicit else int(standard)
    active: dict[int, str] = {}
    children: dict[tuple[str, int, str], int] = {}
    seen = set(key for key, value in metadata.items() if value not in (None, "", []))
    preface = True
    in_references = False
    unnumbered_hierarchy = any(b.level > 1 and not b.features["numbering_family"] for b in blocks)
    for index, b in enumerate(blocks):
        f = b.features
        family = f["numbering_family"]
        b.features["preface"] = preface
        candidates = {"body-paragraph": RoleCandidate(role="body-paragraph")}

        def add(role: str, feature: str, points: float, reason: str, *, context: bool = False) -> None:
            candidate = candidates.setdefault(role, RoleCandidate(role=role))
            contribute(candidate, config, feature, points, reason, context=context)

        add("body-paragraph", "nonempty", 45, "正文为所有可处理块的基础候选")
        if f.get("metadata_content"):
            add(str(f["metadata_content"]), "label_content", 190, "独立元数据标签后的内容", context=True)
        elif b.protected:
            role = "body-table" if b.kind in {"table", "html_block"} and "<table" in b.inline.lower() or b.kind == "table" else "preserved"
            add(role, "parser_protection", 200, "解析结构保留表格、代码、引用、脚注与真实列表")
        else:
            if b.level:
                add(f"heading-{b.level}", "explicit_markdown", 130, "明确 Markdown 标题级别")
            if f["body_sentence"] or len(b.text) > 80:
                add("body-paragraph", "prose", 35, "句末标点、动作语句或长文字提供正文证据")
            next_block = blocks[index + 1] if index + 1 < len(blocks) else None
            caption = _CAPTION.match(b.text)
            if caption:
                add("table-caption" if caption.group(1).lower() in {"表", "table"} else "figure-caption", "caption_label", 160, "显式图表编号题注")
            if _REFERENCE.fullmatch(b.text):
                add("reference-heading", "reference_label", 180, "显式参考文献区域边界")
            elif in_references and not b.level:
                add("reference-entry", "reference_context", 120, "参考文献标题之后的条目", context=True)
            if family:
                numbered_title = _unescape_ordered_heading_marker(b.inline).strip()
                eligible = b.level or _looks_like_bare_heading_text(numbered_title, family)
                if not b.level and _BODY_WORDS.search(b.text):
                    eligible = False
                following_family = next_block.features["numbering_family"] if next_block else None
                has_context = bool(active or "title" in seen or families[family] > 1 or following_family or standard)
                # A true single list after an unnumbered section is preserved;
                # numbered parents/children provide independent outline evidence.
                if b.kind == "ordered_list" and not following_family and not any(
                    _heading_kind(t, standard_document=standard) for t in active.values()
                ):
                    eligible = False
                target = _heading_level_for_title(
                    numbered_title, active, b.level, children, standard_document=standard,
                )
                if preserve_explicit and b.level:
                    target = b.level
                elif family == "decimal":
                    number = re.match(r"\d+(?:\s*\.\s*\d+)+", numbered_title)
                    assert number is not None
                    target = number.group().count(".") + 1 + decimal_offset
                elif family in anchors:
                    target = anchors[family]
                target = max(1, min(6, target))
                if eligible and (b.level or has_context):
                    role = f"heading-{target}"
                    add(role, "number_family", 35, f"编号家族 {family}")
                    add(role, "short_heading", 15, "短编号标题")
                    add(role, "no_terminal", 10, "没有正文句末标点")
                    add(role, "document_sequence", 15, "全文编号家族、相邻子项或父级锚点一致", context=True)
                    if b.level and target != b.level:
                        add(role, "flattened_hierarchy", 100, "同级扁平 Markdown 标记由全文编号重建", context=True)
                elif not b.level:
                    add("body-paragraph", "numbered_prose", 40, "编号本身不足以把正文或列表提升为标题")

            if preface and not family and not caption and not _REFERENCE.fullmatch(b.text):
                label = _LABEL.match(b.inline.strip())
                if label:
                    name, value = label.groups()
                    if name in {"摘要", "关键词"}:
                        role = "abstract-label" if name == "摘要" else "keywords-label"
                    else:
                        key, value = _metadata_label_value(name, value)
                        role = {"authors": "author"}.get(key or "", key or "")
                    key = METADATA_ROLE_KEYS.get(role)
                    if key and key not in seen and value.strip():
                        b.metadata_value = value.strip()
                        add(role, "explicit_label", 185, f"明确{name}标签")
                elif b.text in {"摘要", "关键词"} and next_block and not next_block.protected and not next_block.level and not next_block.features["numbering_family"]:
                    role = "abstract-label" if b.text == "摘要" else "keywords-label"
                    key = METADATA_ROLE_KEYS[role]
                    if key not in seen:
                        b.metadata_value = next_block.inline
                        next_block.features["metadata_content"] = "abstract-content" if role == "abstract-label" else "keywords-content"
                        add(role, "standalone_label", 185, "独立标签与相邻内容段")
                elif "title" in seen:
                    inferred = _infer_title_area_role(b.text)
                    if not inferred and _is_date_candidate(b.text):
                        inferred = "date"
                    role = {"authors": "author"}.get(inferred or "", inferred or "")
                    if inferred and inferred not in seen and b.end - b.start <= 2:
                        b.metadata_value = b.inline
                        add(role, "title_area_shape", 155 if b.level else 90, "题名后的单位、部门、姓名或日期形态")
                    elif "subtitle" not in seen and _is_subtitle_candidate([b.text]) and (
                        not b.level or _SUBTITLE.match(b.text)
                    ):
                        b.metadata_value = b.inline
                        add("document-subtitle", "subtitle_shape", 70, "题名之后的短副标题")
                        add("document-subtitle", "title_neighbor", 15, "连续文前区中的副标题位置", context=True)
                elif index == 0 and b.kind in {"heading", "paragraph"} and not f["body_sentence"]:
                    explicit_title = b.level == 1 and b.text not in {"目次", "目录"} and (not unnumbered_hierarchy or bool(_TITLE_SUFFIX.search(b.text)) or bool(next_block and next_block.features["numbering_family"]))
                    plain_title = bool(_TITLE_SUFFIX.search(b.text)) and next_block is not None and bool(
                        _LABEL.match(next_block.inline.strip()) or next_block.features["numbering_family"] or _SUBTITLE.match(next_block.text)
                    )
                    if explicit_title or plain_title:
                        b.metadata_value = b.inline
                        add("document-title", "leading_title", 150 if explicit_title else 95, "首个题名与后续正文/元数据结构一致")

        b.candidates = sorted(candidates.values(), key=lambda c: c.resolved_score, reverse=True)
        top, runner = b.candidates[0], b.candidates[1] if len(b.candidates) > 1 else RoleCandidate(role="unknown")
        b.score, b.margin = top.resolved_score, top.resolved_score - runner.resolved_score
        b.role = top.role
        b.confidence_band = "high" if b.score >= config.high_score and b.margin >= config.high_margin else "medium" if b.score >= config.medium_score and b.margin > config.ambiguous_margin else "low"
        b.reason = "；".join(e.reason for e in top.evidence)
        if b.role.startswith("heading-"):
            level = int(b.role[-1])
            active = {depth: title for depth, title in active.items() if depth < level}
            active[level] = b.text
            preface = False
            in_references = False
        elif b.role == "reference-heading":
            preface = False
            in_references = True
        elif b.role in METADATA_ROLE_KEYS:
            seen.add(METADATA_ROLE_KEYS[b.role])
            if b.metadata_value is None:
                b.metadata_value = b.inline
        elif b.role in {"abstract-content", "keywords-content"}:
            pass
        elif not is_standard_code_line(b.text):
            preface = False
    return blocks, {
        "numbering_families": dict(families), "explicit_anchors": anchors,
        "preserve_explicit_hierarchy": preserve_explicit, "decimal_level_offset": decimal_offset, "technical_standard": standard,
        "scoring_config": config.model_dump(), "score_semantics": "heuristic-strength-not-probability",
    }
