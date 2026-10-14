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
    _looks_like_technical_standard,
    _unescape_ordered_heading_marker,
    is_standard_code_line,
)
from doc_converter.normalizer import (
    _is_date_candidate,
    _is_subtitle_candidate,
    _metadata_label_value,
)
from doc_converter.structure.hierarchy_resolver import HierarchyRegime, resolve_hierarchy
from doc_converter.structure.numbering import numbering, ordinal

_LABEL = re.compile(
    r"^(作者单位|作者|单位|机构|组织|部门|所属部门|日期|时间|发布时间|摘要|关键词)\s*[:：]\s*([\s\S]*)$"
)
_CAPTION = re.compile(
    r"^(表|图|fig(?:ure)?\.?|table)\s*(?:\d+(?:[.-]\d+)*|[一二三四五六七八九十]+)\s*(?:[：:、.．)）\s]|$)",
    re.I,
)
_REFERENCE = re.compile(
    r"^(?:(?:\d+|[一二三四五六七八九十]+)[、.．)\s]*|[（(](?:\d+|[一二三四五六七八九十]+)[）)]\s*)?(?:参考文献|参考资料|references?)\s*[:：]?$",
    re.I,
)
_SENTENCE = re.compile(r"[。；;，,！？!?：:.]$")
_BODY_WORDS = re.compile(
    r"应当|不得|需要|负责|确保|应按照|应根据|宜采用|由.+组织|按照.+(?:要求|装箱|执行)"
)
_TITLE_SUFFIX = re.compile(r"(?:方案|报告|研究|计划|标题|规范书|总结|测试|标准)$")
_SUBTITLE = re.compile(r"^(?:——|—|--|基于|关于|以.+为)")

METADATA_ROLE_KEYS = {
    "document-title": "title",
    "document-subtitle": "subtitle",
    "organization": "organization",
    "department": "department",
    "author": "authors",
    "date": "date",
    "abstract-label": "abstract",
    "keywords-label": "keywords",
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
    inline_parser = MarkdownIt()
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
                nested |= child.type in {
                    "bullet_list_open",
                    "ordered_list_open",
                    "fence",
                    "code_block",
                    "blockquote_open",
                }
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
            cuts = [start] + [
                i
                for i in range(start + 1, end)
                if _LABEL.match(lines[i].strip())
                or lines[i].strip() in {"摘要", "关键词"}
                or lines[i - 1].strip() in {"摘要", "关键词"}
            ]
            if len(cuts) > 1:
                boundaries = cuts + [end]
                spans = [
                    (left, right, "\n".join(lines[left:right]))
                    for left, right in zip(boundaries, boundaries[1:])
                ]
        for left, right, raw_inline in spans:
            text_tokens = inline_parser.parseInline(raw_inline)
            inline_children = text_tokens[0].children or []
            plain = "".join(
                child.content if child.type != "softbreak" else "\n"
                for child in inline_children
                if child.type in {"text", "code_inline", "image", "softbreak"}
            )
            is_protected = protected or any(
                re.match(r"^\s*\[\^[^]]+\]:|^\s*\[[^]]+\]:", line) for line in lines[left:right]
            )
            blocks.append(
                MarkdownBlock(left, right, kind, plain.strip(), raw_inline, level, is_protected)
            )
        index += 1
    return blocks


_APPENDIX = re.compile(r"^(?:附录|附件)(?:[A-Za-zＡ-Ｚ\d一二三四五六七八九十]+)?(?:[\s：:、.]|$)")
_ORGANIZATION = re.compile(
    r"(?:公司|集团|中心|大学|学院|研究院|事务所|工厂|医院|学校|协会|委员会)$"
)
_DEPARTMENT = re.compile(r"(?:部|部门|处|科|室|局|办公室|厅|所|组|队)$")
_STRONG_PROSE = re.compile(
    r"(?:应当|不得|应按照|应根据|宜采用|由.+组织|按照.+(?:要求|装箱|执行)|需要(?:按照|根据)|负责.+(?:登记|核对|组织)|确保.+(?:到达|完成))"
)


def _add(
    candidates: dict[str, RoleCandidate],
    config: ScoringConfig,
    role: str,
    feature: str,
    points: float,
    reason: str,
    *,
    context: bool = False,
) -> None:
    contribute(
        candidates.setdefault(role, RoleCandidate(role=role)),
        config,
        feature,
        points,
        reason,
        context=context,
    )


def _metadata_shape(text: str) -> str | None:
    # Name suffixes are evidence; occurrences inside section names are not.
    if len(text) <= 80 and _ORGANIZATION.search(text):
        return "organization"
    if len(text) <= 40 and _DEPARTMENT.search(text):
        return "department"
    if _is_date_candidate(text):
        return "date"
    from doc_converter.normalizer import _is_author_candidate

    return "authors" if _is_author_candidate(text) else None


def _structure_features(b: MarkdownBlock, index: int) -> dict[str, Any]:
    f = b.features
    text = _unescape_ordered_heading_marker(b.text).strip()
    family, _, token = numbering(text)
    path = ordinal(token)
    if f["numbering_family"] == "part":
        family, path = "PART", ordinal(text)
    elif f["numbering_family"] == "letter":
        family, path = "ARABIC_ENUM", [ord(text[0].upper()) - ord("A") + 1]
    blocked = b.protected or b.role in METADATA_ROLE_KEYS or b.role.endswith("-content")
    native = (b.level or None) if not f.get("flattened_scope") and not blocked else None
    return {
        "element_id": f"md-{index}",
        "text": b.text,
        "text_length": len(b.text),
        "numbering_family": family,
        "numbering_path": path,
        "numbering_ordinal": path[-1] if path else None,
        "numbering_suffix_letter": f["numbering_family"] == "letter",
        "bare_numeric_root": bool(re.match(r"^\d+\s+", text)),
        "body_sentence": f["strong_body_sentence"] and not b.level,
        "short_text": len(b.text) <= 160,
        "table_context": "table" if b.kind == "table" else None,
        "list": b.protected and b.kind in {"ordered_list", "bullet_list"},
        "has_complex_object": blocked,
        "has_manual_break": False,
        "has_section_break": False,
        "hierarchy_reset_marker": bool(_APPENDIX.match(b.text) or f.get("scope_start"))
        and not blocked,
        "reference_boundary": b.role == "reference-heading",
        "relative_heading_marker": b.text in {"前言", "总则", "概述", "说明"},
        "explicit_author_label": b.role == "author",
        "explicit_organization_label": b.role in {"organization", "department"},
        "explicit_date": b.role == "date",
        "person_name_pattern": False,
        "organization_pattern": False,
        "author_name_list_shape": False,
        "caption_pattern": b.role in {"table-caption", "figure-caption"},
        "native_title_style": "title" if b.role == "document-title" else None,
        "native_heading_level": native,
        "outline_level": None,
        "based_on_heading": False,
        # Missing Markdown format facts remain unknown, never synthesized Word evidence.
        "original_style_id": b.kind,
        "alignment": None,
        "dominant_font_size_pt": None,
        "dominant_bold": None,
        "indentation": None,
        "fully_quoted_content": bool(
            token and re.fullmatch(r"\s*《[^》]+》\s*", text[len(token) :])
        ),
        "reliable_explicit_anchor": bool(native),
        "markdown_index": index,
    }


def analyze_markdown(
    lines: list[str],
    metadata: dict[str, Any],
    line_map: list[int],
    config: ScoringConfig | None = None,
    *,
    canonical: bool = False,
) -> tuple[list[MarkdownBlock], dict[str, Any]]:
    """Local role candidates → shared structural recovery → final role competition."""
    config = config or ScoringConfig()
    blocks = parse_blocks(lines)
    standard = _looks_like_technical_standard("\n".join(lines))
    for b in blocks:
        title = _unescape_ordered_heading_marker(b.inline).strip()
        family = _heading_kind(title, standard_document=standard)
        strong = bool(_SENTENCE.search(b.text) or _STRONG_PROSE.search(b.text))
        b.features = {
            "parser_kind": b.kind,
            "explicit_level": b.level,
            "render_text": b.text,
            "numbering_family": family,
            "short_text": len(b.text) <= 80,
            "terminal_punctuation": bool(_SENTENCE.search(b.text)),
            "body_sentence": strong,
            "strong_body_sentence": strong,
            "weak_body_words": bool(_BODY_WORDS.search(b.text)),
            "protected": b.protected,
            "source_line": line_map[b.start],
        }
    seen = {key for key, value in metadata.items() if value not in (None, "", [])}
    preface = True
    references = False
    postface = False
    unnumbered_hierarchy = any(b.level > 1 and not b.features["numbering_family"] for b in blocks)
    # Stage 1: local evidence and metadata order. No permanent numbered level decisions.
    for index, b in enumerate(blocks):
        f = b.features
        family = f["numbering_family"]
        f["preface"] = preface
        if _APPENDIX.match(b.text) or _REFERENCE.fullmatch(b.text):
            postface = True
        f["region"] = "preface" if preface else "postface" if postface else "body"
        candidates: dict[str, RoleCandidate] = {}

        def add(
            role: str, feature: str, points: float, reason: str, *, context: bool = False
        ) -> None:
            _add(candidates, config, role, feature, points, reason, context=context)

        add("body-paragraph", "nonempty", 45, "正文为所有可处理块的基础候选")
        next_block = blocks[index + 1] if index + 1 < len(blocks) else None
        caption = _CAPTION.match(b.text)
        if f.get("metadata_content"):
            add(
                str(f["metadata_content"]),
                "label_content",
                190,
                "独立元数据标签后的内容",
                context=True,
            )
        elif b.protected:
            add(
                "body-table"
                if b.kind == "table" or b.kind == "html_block" and "<table" in b.inline.lower()
                else "preserved",
                "parser_protection",
                200,
                "保留表格、代码、引用、脚注及真实列表语法",
            )
        else:
            for level in range(1, 7):
                add(
                    f"heading-{level}",
                    "number_family",
                    35 if family else 0,
                    "编号仅产生候选，实际级别待结构树判断",
                )
                if family:
                    add(
                        f"heading-{level}",
                        "heading_shape",
                        15 if len(b.text) <= 80 else 5,
                        "标题长度为强弱证据，无35字绝对门槛",
                    )
                    add(
                        f"heading-{level}",
                        "no_terminal",
                        10 if not f["terminal_punctuation"] else -40,
                        "句末标点证据",
                    )
                    if f["strong_body_sentence"] and not b.level:
                        add(
                            f"heading-{level}",
                            "numbered_prose",
                            -80,
                            "完整动作句或句末标点是正文证据",
                        )
            if b.level:
                add(f"heading-{b.level}", "explicit_markdown", 130, "显式 Markdown 标题锚点")
            if f["strong_body_sentence"] or len(b.text) > 160:
                add("body-paragraph", "prose", 35, "完整正文句或长段落证据")
            if caption:
                role = (
                    "table-caption"
                    if caption.group(1).lower() in {"表", "table"}
                    else "figure-caption"
                )
                add(role, "caption_label", 160, "显式图表编号题注")
                neighbor = (
                    next_block
                    if next_block
                    and (
                        next_block.kind == "table"
                        or "![" in next_block.inline
                        or "<img" in next_block.inline.lower()
                    )
                    else blocks[index - 1]
                    if index
                    else None
                )
                matched = bool(
                    neighbor
                    and (
                        role == "table-caption"
                        and neighbor.kind == "table"
                        or role == "figure-caption"
                        and ("![" in neighbor.inline or "<img" in neighbor.inline.lower())
                    )
                )
                f["caption_neighbor_matched"] = matched
                if matched:
                    add(role, "caption_neighbor", 20, "相邻表格或图片支持题注", context=True)
            if _REFERENCE.fullmatch(b.text):
                add("reference-heading", "reference_label", 180, "参考文献区域边界")
            elif references and not b.level and not _APPENDIX.match(b.text):
                add(
                    "reference-entry",
                    "reference_context",
                    120,
                    "参考文献边界内的条目",
                    context=True,
                )
            if _APPENDIX.match(b.text):
                add(
                    "heading-1",
                    "appendix_boundary",
                    180,
                    "附件/附录是独立文后结构边界",
                    context=True,
                )
                f["region"] = "postface"
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
                elif (
                    b.text in {"摘要", "关键词"}
                    and next_block
                    and not next_block.protected
                    and not next_block.level
                    and not next_block.features["numbering_family"]
                ):
                    role = "abstract-label" if b.text == "摘要" else "keywords-label"
                    key = METADATA_ROLE_KEYS[role]
                    if key not in seen:
                        b.metadata_value = next_block.inline
                        next_block.features["metadata_content"] = (
                            "abstract-content" if role == "abstract-label" else "keywords-content"
                        )
                        add(role, "standalone_label", 185, "独立标签与相邻内容段")
                elif "title" in seen:
                    inferred = _metadata_shape(b.text)
                    role = {"authors": "author"}.get(inferred or "", inferred or "")
                    followup = next_block and (
                        _LABEL.match(next_block.inline.strip())
                        or _metadata_shape(next_block.text)
                        or next_block.text == "摘要"
                    )
                    if (
                        inferred
                        and inferred not in seen
                        and b.end - b.start <= 2
                        and (inferred != "authors" or followup)
                    ):
                        b.metadata_value = b.inline
                        add(
                            role,
                            "title_area_shape",
                            155 if b.level else 90,
                            "题名后的名称后缀及顺序证据",
                        )
                    elif (
                        "subtitle" not in seen
                        and _is_subtitle_candidate([b.text])
                        and (
                            _SUBTITLE.match(b.text)
                            or not b.level
                            and next_block
                            and _LABEL.match(next_block.inline.strip())
                        )
                    ):
                        b.metadata_value = b.inline
                        add("document-subtitle", "subtitle_shape", 70, "题名之后的副标题形态")
                        add(
                            "document-subtitle",
                            "title_neighbor",
                            15,
                            "文前副标题位置",
                            context=True,
                        )
                elif (
                    index == 0
                    and b.kind in {"heading", "paragraph"}
                    and not f["strong_body_sentence"]
                ):
                    explicit_title = (
                        b.level == 1
                        and b.text not in {"目次", "目录"}
                        and (
                            not unnumbered_hierarchy
                            or bool(_TITLE_SUFFIX.search(b.text))
                            or bool(next_block and next_block.features["numbering_family"])
                        )
                    )
                    plain_title = (
                        bool(_TITLE_SUFFIX.search(b.text))
                        and next_block is not None
                        and bool(
                            _LABEL.match(next_block.inline.strip())
                            or next_block.features["numbering_family"]
                            or _SUBTITLE.match(next_block.text)
                        )
                    )
                    if explicit_title or plain_title:
                        b.metadata_value = b.inline
                        add(
                            "document-title",
                            "leading_title",
                            150 if explicit_title else 95,
                            "首个题名与后续正文/元数据结构一致",
                        )
        b.candidates = list(candidates.values())
        top = max(b.candidates, key=lambda c: c.resolved_score)
        b.role = top.role
        if b.role in METADATA_ROLE_KEYS:
            seen.add(METADATA_ROLE_KEYS[b.role])
            b.metadata_value = b.metadata_value or b.inline
        elif b.role.endswith("-content"):
            pass
        else:
            if not is_standard_code_line(b.text):
                preface = False
            if b.role == "reference-heading":
                references = True
            elif _APPENDIX.match(b.text) or b.role.startswith("heading-"):
                references = False

    # Local source scopes: major chapters and appendices may use different schemes.
    scope = 0
    scopes: defaultdict[int, list[MarkdownBlock]] = defaultdict(list)
    for i, b in enumerate(blocks):
        if i and (
            _APPENDIX.match(b.text)
            or b.features["numbering_family"] in {"chapter", "part"}
            and not (scopes[scope] and scopes[scope][0].features["numbering_family"] == "part")
            or b.level == 1
            and b.role != "document-title"
            and not b.features["numbering_family"]
        ):
            scope += 1
            b.features["scope_start"] = True
        b.features["markdown_scope"] = scope
        scopes[scope].append(b)
    for members in scopes.values():
        numbered = [b for b in members if b.level and b.features["numbering_family"]]
        flattened = (
            not canonical
            and len(numbered) > 1
            and len({b.level for b in numbered}) == 1
            and len({b.features["numbering_family"] for b in numbered}) > 1
        )
        for b in members:
            b.features["flattened_scope"] = flattened
    structural = [_structure_features(b, i) for i, b in enumerate(blocks)]
    chapter_scopes = {
        scope_id
        for scope_id, members in scopes.items()
        if any(b.features["numbering_family"] in {"chapter", "part"} for b in members)
    }
    for f in structural:
        members = scopes[blocks[f["markdown_index"]].features["markdown_scope"]]
        if blocks[f["markdown_index"]].features["markdown_scope"] in chapter_scopes:
            f["bare_numeric_root"] = False
    scratch = [
        [RoleCandidate(role=f"heading-{i}") for i in range(1, 7)]
        + [RoleCandidate(role="body-paragraph"), RoleCandidate(role="unknown")]
        for _ in blocks
    ]

    def qualification_transform(features: list[dict[str, Any]]) -> None:
        qualified: dict[tuple[int, str], dict[str, Any]] = {}
        previous_heading: dict[int, dict[str, Any]] = {}
        active_paths: dict[tuple[int, tuple[int, ...]], dict[str, Any]] = {}
        for f in features:
            b = blocks[f["markdown_index"]]
            scope_id = b.features["markdown_scope"]
            family = f["numbering_family"]
            previous = previous_heading.get(scope_id)
            if (
                f["manual_sequence_uncertain"]
                and previous
                and family == "CIRCLED"
                and len({key[1] for key in qualified if key[0] == scope_id}) >= 3
            ):
                f["manual_sequence_uncertain"] = False
            if b.level and b.features["flattened_scope"] and not f["has_complex_object"]:
                f["manual_sequence_candidate"] = False
                f["manual_sequence_uncertain"] = False
                f["heading_candidate"] = True
            safe = (
                not any(
                    f[k]
                    for k in (
                        "list",
                        "has_complex_object",
                        "body_sentence",
                        "manual_sequence_candidate",
                        "manual_sequence_uncertain",
                    )
                )
                and f["short_text"]
            )
            if safe and family in {"CN_ENUM", "PART"} and f["has_child_content_before_next_peer"]:
                f["heading_candidate"] = True
            if safe and family and not f["heading_candidate"]:
                peer = qualified.get((scope_id, family))
                path = tuple(f["numbering_path"])
                parent = active_paths.get((scope_id, path[:-1])) if family == "DECIMAL" else None
                # A leaf may close an established peer series or extend a real numeric parent.
                # This is independent of mere title presence or global family frequency.
                previous = previous_heading.get(scope_id)
                order = [
                    "PART",
                    "CHAPTER",
                    "SECTION",
                    "CN_ENUM",
                    "CN_BRACKET",
                    "ARABIC_ENUM",
                    "ARABIC_BRACKET",
                    "CIRCLED",
                ]
                nested_leaf = bool(
                    previous
                    and family in order
                    and previous["numbering_family"] in order
                    and order.index(family) > order.index(previous["numbering_family"])
                    and (
                        len({key[1] for key in qualified if key[0] == scope_id}) >= 3
                        or previous["numbering_family"] in {"PART", "CHAPTER", "SECTION"}
                    )
                )
                escaped = bool(
                    re.match(r"^\d+\\[.)]", b.inline)
                    and len(b.text) <= 80
                    and not f["body_sentence"]
                )
                if (
                    nested_leaf
                    or escaped
                    or parent
                    or peer
                    and f["numbering_ordinal"] == (peer["numbering_ordinal"] or 0) + 1
                ):
                    f["heading_candidate"] = True
            if f["heading_candidate"] and family:
                previous_heading[scope_id] = f
                qualified[scope_id, family] = f
                active_paths[scope_id, tuple(f["numbering_path"])] = f

    scope_decimal_offsets: dict[int, int] = {}
    for scope_id, members in scopes.items():
        offsets = [
            b.level - len(ordinal(numbering(b.text)[2]))
            for b in members
            if b.level
            and not b.features["flattened_scope"]
            and b.features["numbering_family"] == "decimal"
        ]
        if offsets:
            scope_decimal_offsets[scope_id] = Counter(offsets).most_common(1)[0][0]
    regime_offsets: dict[tuple[int, str], int] = {}

    def level_transform(f: dict[str, Any], r: HierarchyRegime, base: int, level: int) -> int:
        b = blocks[f["markdown_index"]]
        scope_id = b.features["markdown_scope"]
        members = scopes[scope_id]
        if f["recovered_outline_level"]:
            return int(f["recovered_outline_level"])
        if f["native_heading_level"]:
            return int(f["native_heading_level"])
        if b.features["numbering_family"] in {"part", "chapter", "section"} and any(
            x.features["numbering_family"] == "part" for x in members
        ):
            return {"part": 1, "chapter": 2, "section": 3}[b.features["numbering_family"]]
        first_family = next(
            (x.features["numbering_family"] for x in members if x.features["numbering_family"]),
            None,
        )
        if (
            b.features["flattened_scope"]
            and first_family in {"arabic", "standard-root"}
            and f["numbering_family"] in {"ARABIC_ENUM", "CN_BRACKET", "ARABIC_BRACKET"}
        ):
            return {"ARABIC_ENUM": 1, "CN_BRACKET": 2, "ARABIC_BRACKET": 3}[f["numbering_family"]]
        if b.features["numbering_family"] == "letter":
            predecessors = [
                x
                for x in structural[: f["markdown_index"]]
                if x.get("effective_heading_level")
                and blocks[x["markdown_index"]].features["numbering_family"] != "letter"
                and blocks[x["markdown_index"]].features["markdown_scope"] == scope_id
            ]
            if predecessors:
                return int(predecessors[-1]["effective_heading_level"]) + 1
        if f["numbering_family"] == "DECIMAL" and scope_id in scope_decimal_offsets:
            return len(f["numbering_path"]) + scope_decimal_offsets[scope_id]
        if (
            members
            and _APPENDIX.match(members[0].text)
            and f["numbering_family"] is not None
            and base == 0
        ):
            return level + 1
        key = scope_id, r.regime_id
        if key not in regime_offsets:
            offsets = [
                structural[i]["native_heading_level"]
                - base
                - r.compressed_levels[structural[i]["numbering_family"]]
                for i in r.indices
                if structural[i]["native_heading_level"]
                and structural[i]["numbering_family"] in r.compressed_levels
                and blocks[i].features["markdown_scope"] == scope_id
            ]
            regime_offsets[key] = Counter(offsets).most_common(1)[0][0] if offsets else 0
        return level + regime_offsets[key]

    hierarchy = resolve_hierarchy(
        structural,
        scratch,
        ScoringConfig(),
        qualification_transform=qualification_transform,
        level_transform=level_transform,
    )
    # Stage 3: only input-specific weights determine final roles.
    for b, f in zip(blocks, structural, strict=True):
        b.features["structure"] = dict(f)
        for key in (
            "element_id",
            "heading_candidate",
            "manual_sequence_candidate",
            "manual_sequence_uncertain",
            "hierarchy_regime_id",
            "hierarchy_schema",
            "effective_heading_level",
            "effective_parent_id",
            "parent_resolution_type",
            "source_defect_type",
            "hierarchy_evidence",
            "local_hierarchy_warning",
        ):
            b.features[key] = f.get(key)
        candidates = {c.role: c for c in b.candidates}
        if f["recovery_force_preserve"]:
            b.protected = True
            b.features["preservation_reason"] = "broken-numbering-conflict"
            _add(
                candidates,
                config,
                "preserved",
                "confirmed_source_conflict",
                250,
                "源编号及显式层级序列矛盾，保留原语法并记录冲突",
                context=True,
            )
        level = f["effective_heading_level"]
        if (
            not b.protected
            and b.role not in METADATA_ROLE_KEYS
            and not b.role.endswith("-content")
            and b.role != "reference-heading"
        ):
            if f["heading_candidate"] and level is not None:
                for c in b.candidates:
                    if c.role.startswith("heading-"):
                        target = c.role == f"heading-{level}"
                        _add(
                            candidates,
                            config,
                            c.role,
                            "resolved_structure",
                            15 if target else -120,
                            f"共享章节树 {f['hierarchy_schema']}/{f['hierarchy_regime_id']} 给出H{level}",
                            context=True,
                        )
                        if target and (
                            f["recovered_heading_family"] or b.features["flattened_scope"]
                        ):
                            _add(
                                candidates,
                                config,
                                c.role,
                                "source_recovery",
                                145,
                                "源结构恢复证据支持自动修正",
                                context=True,
                            )
            elif f["manual_sequence_candidate"] or f["manual_sequence_uncertain"]:
                for c in b.candidates:
                    if c.role.startswith("heading-"):
                        _add(
                            candidates,
                            config,
                            c.role,
                            "manual_sequence",
                            -160,
                            "平行编号缺少各项子正文，是人工列表",
                            context=True,
                        )
            elif not b.level:
                for c in b.candidates:
                    if c.role.startswith("heading-"):
                        _add(
                            candidates,
                            config,
                            c.role,
                            "unqualified_structure",
                            -80,
                            "编号未获得章节结构资格",
                            context=True,
                        )
        b.candidates = sorted(candidates.values(), key=lambda c: c.resolved_score, reverse=True)
        top = b.candidates[0]
        runner = b.candidates[1] if len(b.candidates) > 1 else RoleCandidate(role="unknown")
        b.role, b.score, b.margin = (
            top.role,
            top.resolved_score,
            top.resolved_score - runner.resolved_score,
        )
        b.confidence_band = (
            "high"
            if b.score >= config.high_score and b.margin >= config.high_margin
            else "medium"
            if b.score >= config.medium_score and b.margin > config.ambiguous_margin
            else "low"
        )
        b.reason = "；".join(e.reason for e in top.evidence)
    return blocks, {
        **hierarchy,
        "numbering_families": dict(
            Counter(
                b.features["numbering_family"] for b in blocks if b.features["numbering_family"]
            )
        ),
        "technical_standard": standard,
        "scoring_config": config.model_dump(),
        "stages": ["local-candidates", "shared-document-structure", "final-role-decision"],
        "score_semantics": "heuristic-strength-not-probability",
    }
