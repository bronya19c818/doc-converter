"""Deterministic Markdown normalization without model-assisted rewriting."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

import yaml
from markdown_it import MarkdownIt

from doc_converter.markdown_preprocess import preprocess_markdown

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_SPLIT_IMAGE_LABEL_LINE = re.compile(r"^([ \t]*!\[[^\]\r\n]*\])[ \t]*$")
_SPLIT_IMAGE_DESTINATION_LINE = re.compile(r"^[ \t]*(\([^\r\n]+\))[ \t]*$")
_INLINE_CODE_PATTERN = re.compile(r"(`+)[\s\S]*?\1")
_HTML_IMAGE_TAG_PATTERN = re.compile(
    r"<img\b(?:[^\"'>]|\"[^\"]*\"|'[^']*')*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_SUB_SUP_PATTERN = re.compile(
    r"<(?P<tag>sub|sup)\b[^>]*>(?P<content>.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_LABEL_PATTERN = re.compile(r"^\s*(摘要|关键词)\s*[:：]\s*(.*)$")

_KEYWORD_SEPARATOR = re.compile(r"[；;，,\n]+")
_TABLE_CAPTION_PATTERN = re.compile(
    r"^\s*表\s*(?:\d+|[一二三四五六七八九十百千万]+)\s*(?:[：:、.．\s]|$)"
)

_CHINESE_NAME_PATTERN = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
_MULTI_AUTHOR_PATTERN = re.compile(r"^[\u4e00-\u9fff]{2,4}(?:[、，,]\s*[\u4e00-\u9fff]{2,4})+$")
_ORG_MARKERS = ("公司", "集团", "中心", "大学", "学院", "研究院", "事务所", "工厂", "医院", "学校", "协会", "委员会")
_DEPARTMENT_MARKERS = ("部门", "部", "处", "科", "室", "局", "办", "厅", "所", "组", "队")
_DATE_PATTERN = re.compile(
    r"^(?:\d{4}\s*[年/-]\s*\d{1,2}\s*[月/-]\s*\d{1,2}\s*(?:日)?|\d{4}[.]\d{1,2}[.]\d{1,2})$"
)
_COMMON_SURNAMES = frozenset(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴郁胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公晋楚闫法汝鄢涂钦岳帅缑亢况郈有琴归海"
)


@dataclass(frozen=True)
class NormalizedDocument:
    """A normalized document and the audit data created while producing it."""

    markdown: str
    report: dict[str, Any]
    metadata: dict[str, Any]


_METADATA_KEYS = (
    "title",
    "subtitle",
    "organization",
    "department",
    "authors",
    "date",
    "abstract",
    "keywords",
)


def normalize_markdown(
    source: str,
    *,
    filename: str,
    confirmed_roles: dict[int, str] | None = None,
) -> NormalizedDocument:
    """Automatically score, resolve and normalize immutable imported Markdown.

    The optional legacy argument is accepted only for Python callers during
    migration. Decisions always come from the same automatic pipeline.
    """
    from doc_converter.markdown_scoring import METADATA_ROLE_KEYS, analyze_markdown

    raw_metadata, content_lines, first_content_line = _extract_front_matter(source)
    preprocessed = preprocess_markdown(
        "\n".join(content_lines) + ("\n" if content_lines else ""),
        line_map=[first_content_line + offset for offset in range(len(content_lines))],
        normalize_structure=False,
    )
    content_lines = preprocessed.text.splitlines()
    metadata = _normalize_metadata(raw_metadata)
    blocks, context = analyze_markdown(content_lines, metadata, preprocessed.line_map)
    changes: list[dict[str, Any]] = list(preprocessed.changes)
    replacements: dict[int, tuple[int, list[str]]] = {}
    consumed: set[int] = set()
    from doc_converter.docx_styles import ROLE_TO_STYLE_ID

    decisions: list[dict[str, Any]] = []
    for role, key in METADATA_ROLE_KEYS.items():
        if key not in metadata or metadata[key] in (None, "", []):
            continue
        line = next((i + 1 for i, text in enumerate(source.splitlines()[:first_content_line - 1]) if re.match(rf"^{key}\s*:", text)), 1)
        style_role = "organization-department" if role in {"organization", "department"} else role
        decisions.append({
            "line": line, "end_line": line, "from_role": role, "role": role,
            "target_style": ROLE_TO_STYLE_ID.get(style_role), "action": "mapped",
            "applied_change": False, "before": metadata[key], "after": metadata[key],
            "score": 200, "margin": 200, "confidence_band": "high",
            "reason": "显式 Front Matter 优先", "features": {"front_matter": True},
            "candidates": [{"role": role, "raw_score": 200, "resolved_score": 200, "evidence": [{"feature": "explicit_front_matter", "contribution": 200, "reason": "显式 Front Matter 优先", "stage": "raw"}]}],
        })
    for block in blocks:
        before = "\n".join(content_lines[block.start:block.end])
        original_role = f"heading-{block.level}" if block.level else block.kind
        after = before
        applied = False
        if block.start in consumed:
            role = block.role
        else:
            role = block.role
            if role in METADATA_ROLE_KEYS:
                key = METADATA_ROLE_KEYS[role]
                value = block.metadata_value or block.inline
                if key not in metadata or metadata[key] in (None, "", []):
                    metadata[key] = _split_list_value(value, separators="；;，,、\n") if key == "authors" else _split_list_value(value) if key == "keywords" else value
                    end = block.end
                    if block.text in {"摘要", "关键词"}:
                        next_block = next((b for b in blocks if b.start >= block.end), None)
                        if next_block:
                            end = next_block.end
                    consumed.update(range(block.start, end))
                    replacements[block.start] = (end, [])
                    after = ""
                    applied = True
                    changes.append({"line": preprocessed.line_map[block.start], "from": original_role, "to": role})
            elif role.startswith("heading-") and not block.protected:
                level = int(role[-1])
                if not block.level or level != block.level:
                    from doc_converter.markdown_preprocess import _unescape_ordered_heading_marker
                    after = f"{'#' * level} {_unescape_ordered_heading_marker(block.inline).strip()}"
                    replacements[block.start] = (block.end, [after])
                    applied = True
                    changes.append({"line": preprocessed.line_map[block.start], "from": original_role, "to": "heading-level", "level": level, "reason": block.reason})
        decisions.append({
            "line": preprocessed.line_map[block.start],
            "end_line": preprocessed.line_map[block.end - 1],
            "from_role": original_role, "role": role,
            "target_style": ROLE_TO_STYLE_ID.get("organization-department" if role in {"organization", "department"} else role),
            "action": "preserved" if block.protected and role != "body-table" else "mapped",
            "applied_change": applied, "before": before, "after": after,
            "score": block.score, "margin": block.margin,
            "confidence_band": block.confidence_band, "reason": block.reason,
            "features": block.features,
            "candidates": [candidate.model_dump() for candidate in block.candidates],
        })
    output: list[str] = []
    index = 0
    while index < len(content_lines):
        if index in replacements:
            end, replacement = replacements[index]
            output.extend(replacement)
            index = end
        else:
            output.append(content_lines[index])
            index += 1
    body = _normalize_html_tables("\n".join(output).strip("\n"))
    markdown = _serialize_front_matter(metadata, body)
    integrity = _integrity_inventory(source, markdown)
    integrity["passed"] = integrity["images"] == integrity["normalized_images"] and integrity["links"] == integrity["normalized_links"]
    integrity.pop("normalized_images")
    integrity.pop("normalized_links")
    return NormalizedDocument(
        markdown=markdown,
        report={
            "schema": "normalized-md/v2", "source": filename,
            "changes": changes, "decisions": decisions, "context": context,
            "counts": {"blocks": len(decisions), "changed": sum(d["applied_change"] for d in decisions), "roles": dict(Counter(d["role"] for d in decisions))},
            "warnings": [], "metadata": metadata, "integrity": integrity,
        },
        metadata=metadata,
    )


def _extract_front_matter(source: str) -> tuple[dict[str, Any], list[str], int]:
    lines = source.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}, lines, 1

    for closing_index in range(1, len(lines)):
        if lines[closing_index].strip() == "---":
            loaded = yaml.safe_load("\n".join(lines[1:closing_index])) or {}
            if not isinstance(loaded, dict):
                raise ValueError("YAML Front Matter 必须是对象。")
            return dict(loaded), lines[closing_index + 1 :], closing_index + 2
    return {}, lines, 1


def _serialize_front_matter(metadata: dict[str, Any], body: str) -> str:
    ordered: dict[str, Any] = {"schema": "normalized-md/v1"}
    for key in _METADATA_KEYS:
        if key in metadata and metadata[key] not in (None, "", []):
            ordered[key] = metadata[key]
    unknown = {key: value for key, value in metadata.items() if key not in _METADATA_KEYS and key != "schema"}
    ordered.update(unknown)
    serialized_metadata = yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{serialized_metadata}\n---\n\n{body}\n"


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Coerce supported metadata to stable JSON/YAML-friendly values."""

    normalized: dict[str, Any] = {}
    for key in _METADATA_KEYS:
        if key not in metadata:
            continue
        value = metadata[key]
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        if key in {"authors", "keywords"}:
            if isinstance(value, str):
                value = _split_list_value(value, separators="；;，,、\n" if key == "authors" else "；;，,\n")
            elif isinstance(value, tuple):
                value = list(value)
            elif not isinstance(value, list):
                value = []
            value = [str(item).strip() for item in value if str(item).strip()]
        elif value is not None:
            value = str(value)
        normalized[key] = value
    for key, value in metadata.items():
        if key not in _METADATA_KEYS and key != "schema":
            normalized[key] = value
    return normalized


def _is_subtitle_candidate(lines: list[str]) -> bool:
    if len(lines) != 1:
        return False
    value = lines[0].strip()
    if not 2 <= len(value) <= 80:
        return False
    if _LABEL_PATTERN.match(value) or _HEADING_PATTERN.match(value):
        return False
    if _TABLE_CAPTION_PATTERN.match(value):
        return False
    if value.startswith(("- ", "* ", "+ ", "> ")) or re.match(r"^\d+[.)、]", value):
        return False
    return not value.endswith(("。", "！", "？", "；", ".", "!", "?", ";", ":", "："))


def _split_list_value(value: str, *, separators: str = "；;，,\n") -> list[str]:
    """Split display delimiters while retaining Markdown links/code verbatim."""
    parts: list[str] = []
    start = 0
    brackets = 0
    parentheses = 0
    code = False
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "`":
            code = not code
        if code:
            continue
        if character == "[":
            brackets += 1
        elif character == "]":
            brackets = max(0, brackets - 1)
        elif character == "(":
            parentheses += 1
        elif character == ")":
            parentheses = max(0, parentheses - 1)
        elif character in separators and not brackets and not parentheses:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def _metadata_label_value(label: str, value: str) -> tuple[str | None, str]:
    text = value.strip()
    if not text:
        return None, ""
    if label == "作者":
        return "authors", text
    if label == "作者单位" or label in {"单位", "机构", "组织"}:
        return "organization", text
    if label in {"日期", "时间", "发布时间"}:
        return "date", text
    return "department", text


def _infer_title_area_role(value: str) -> str | None:
    if _is_author_candidate(value):
        return "authors"
    if _is_organization_candidate(value):
        return "organization"
    if _is_department_candidate(value):
        return "department"
    return None


def _is_author_candidate(value: str) -> bool:
    text = value.strip()
    if text and text[0] in _COMMON_SURNAMES and _CHINESE_NAME_PATTERN.fullmatch(text):
        return True
    return bool(_MULTI_AUTHOR_PATTERN.fullmatch(text)) and text[0] in _COMMON_SURNAMES


def _is_organization_candidate(value: str) -> bool:
    return 2 <= len(value) <= 20 and not _has_sentence_punctuation(value) and any(
        marker in value for marker in _ORG_MARKERS
    )


def _is_department_candidate(value: str) -> bool:
    return 2 <= len(value) <= 20 and not _has_sentence_punctuation(value) and any(
        marker in value for marker in _DEPARTMENT_MARKERS
    )


def _is_date_candidate(value: str) -> bool:
    return bool(_DATE_PATTERN.fullmatch(value.strip()))


def _has_sentence_punctuation(value: str) -> bool:
    return any(mark in value for mark in "。！？；;，,：:、.!?")


class _HtmlTableParser(HTMLParser):
    """Parse the simple HTML tables commonly emitted by Markdown exporters."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\ue000")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(_normalize_html_table_cell("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _normalize_html_tables(markdown: str) -> str:
    """Convert simple raw HTML tables into editable Markdown tables."""

    if "<table" not in markdown.lower():
        return markdown
    lines = markdown.splitlines()
    replacements: dict[int, tuple[int, str]] = {}
    for token in MarkdownIt("commonmark", {"html": True}).parse(markdown):
        if token.type == "html_block" and token.level == 0 and token.map and "<table" in token.content.lower():
            start, end = token.map
            replacements[start] = (end, _replace_html_table_block("\n".join(lines[start:end])))
    output: list[str] = []
    index = 0
    while index < len(lines):
        if index in replacements:
            end, replacement = replacements[index]
            output.extend(replacement.splitlines())
            index = end
        else:
            output.append(lines[index])
            index += 1
    return "\n".join(output)


def _replace_html_table_block(block: str) -> str:
    parser = _HtmlTableParser()
    if block.lower().count("<table") > 1 or re.search(r"\b(?:rowspan|colspan)\s*=", block, re.IGNORECASE):
        return block
    parser.feed(block)
    parser.close()
    if not parser.rows:
        return block
    width = max(len(row) for row in parser.rows)
    rows = [row + [""] * (width - len(row)) for row in parser.rows]
    escaped = [
        [cell.replace("|", "\\|").replace("\n", "&#10;") for cell in row]
        for row in rows
    ]
    lines = ["| " + " | ".join(row) + " |" for row in escaped]
    lines.insert(1, "| " + " | ".join("---" for _ in range(width)) + " |")
    return "\n".join(lines)


def _normalize_html_table_cell(value: str) -> str:
    parts = value.split("\ue000")
    normalized = [re.sub(r"\s+", " ", part).strip() for part in parts]
    return "\n".join(part for part in normalized if part)


def _integrity_inventory(source: str, normalized: str) -> dict[str, Any]:
    return {
        "images": _image_destinations(source),
        "normalized_images": _image_destinations(normalized),
        "links": _LINK_PATTERN.findall(source),
        "normalized_links": _LINK_PATTERN.findall(normalized),
    }


def _code_line_indices(markdown: str) -> set[int]:
    return {line for token in MarkdownIt("commonmark", {"html": True}).parse(markdown)
            if token.type in {"fence", "code_block"} and token.map for line in range(*token.map)}


def _join_split_image_syntax(markdown: str) -> str:
    """Join exported image syntax outside parsed code blocks."""
    lines = markdown.splitlines()
    protected = _code_line_indices(markdown)
    output: list[str] = []
    index = 0
    while index < len(lines):
        label = _SPLIT_IMAGE_LABEL_LINE.fullmatch(lines[index])
        if index not in protected and index + 1 < len(lines) and index + 1 not in protected and label:
            destination = _SPLIT_IMAGE_DESTINATION_LINE.fullmatch(lines[index + 1])
            if destination:
                output.append(label.group(1) + destination.group(1))
                index += 2
                continue
        output.append(lines[index])
        index += 1
    return "\n".join(output)


class _ImageSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: list[str] = []
        self.images: list[tuple[str, str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "img":
            return
        attributes = dict(attrs)
        source = attributes.get("src")
        if not isinstance(source, str) or not source:
            return
        alt_value = attributes.get("alt")
        title_value = attributes.get("title")
        alt = alt_value if isinstance(alt_value, str) else ""
        title = title_value if isinstance(title_value, str) else None
        self.sources.append(source)
        self.images.append((source, alt, title))


def _image_destinations(markdown: str) -> list[str]:
    """Inventory Markdown reference, inline, split-line, and raw HTML images."""

    destinations: list[str] = []
    tokens = MarkdownIt("commonmark", {"html": True}).parse(_join_split_image_syntax(markdown))
    for token in tokens:
        fragments: list[str] = []
        if token.type == "html_block":
            fragments.append(token.content)
        elif token.type == "inline":
            for child in token.children or []:
                if child.type == "image":
                    source = child.attrGet("src")
                    if isinstance(source, str) and source:
                        destinations.append(source)
                elif child.type == "html_inline":
                    fragments.append(child.content)
        for fragment in fragments:
            html_parser = _ImageSourceParser()
            html_parser.feed(fragment)
            html_parser.close()
            destinations.extend(html_parser.sources)
    return destinations


def _normalize_html_images(markdown: str) -> str:
    """Convert raw HTML image tags to Markdown so Pandoc embeds them in DOCX."""

    output: list[str] = []
    ordinary_lines: list[str] = []
    protected = _code_line_indices(markdown)

    def flush_ordinary_lines() -> None:
        if ordinary_lines:
            block = "".join(ordinary_lines)
            code_spans: list[str] = []

            def hold_code_span(match: re.Match[str]) -> str:
                code_spans.append(match.group(0))
                return f"\x00doc-converter-inline-code-{len(code_spans) - 1}\x00"

            transformed = _INLINE_CODE_PATTERN.sub(hold_code_span, block)
            transformed = _HTML_IMAGE_TAG_PATTERN.sub(_html_image_to_markdown, transformed)
            for index, code_span in enumerate(code_spans):
                transformed = transformed.replace(f"\x00doc-converter-inline-code-{index}\x00", code_span)
            output.append(transformed)
            ordinary_lines.clear()

    for index, line in enumerate(markdown.splitlines(keepends=True)):
        if index in protected:
            flush_ordinary_lines()
            output.append(line)
        else:
            ordinary_lines.append(line)
    flush_ordinary_lines()
    return "".join(output)


def _normalize_html_sub_sup(markdown: str) -> str:
    """Map DOCX reader HTML sub/sup tags to Pandoc's native extensions."""

    def replace(match: re.Match[str]) -> str:
        content = match.group("content")
        marker = "~" if match.group("tag").casefold() == "sub" else "^"
        return f"{marker}{content}{marker}"

    output: list[str] = []
    ordinary_lines: list[str] = []
    protected = _code_line_indices(markdown)

    def flush_ordinary_lines() -> None:
        if not ordinary_lines:
            return
        block = "".join(ordinary_lines)
        code_spans: list[str] = []

        def hold_code_span(match: re.Match[str]) -> str:
            code_spans.append(match.group(0))
            return f"\x00doc-converter-sub-sup-code-{len(code_spans) - 1}\x00"

        transformed = _INLINE_CODE_PATTERN.sub(hold_code_span, block)
        transformed = _HTML_SUB_SUP_PATTERN.sub(replace, transformed)
        for index, code_span in enumerate(code_spans):
            transformed = transformed.replace(
                f"\x00doc-converter-sub-sup-code-{index}\x00",
                code_span,
            )
        output.append(transformed)
        ordinary_lines.clear()

    for index, line in enumerate(markdown.splitlines(keepends=True)):
        if index in protected:
            flush_ordinary_lines()
            output.append(line)
        else:
            ordinary_lines.append(line)
    flush_ordinary_lines()
    return "".join(output)


def _html_image_to_markdown(match: re.Match[str]) -> str:
    parser = _ImageSourceParser()
    parser.feed(match.group(0))
    parser.close()
    if not parser.images:
        return match.group(0)
    source, alt, title = parser.images[0]
    if "<" in source or ">" in source:
        return match.group(0)
    escaped_alt = alt.replace("\\", "\\\\").replace("]", "\\]").replace("\n", " ")
    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"') if title else None
    title_part = f' "{escaped_title}"' if escaped_title else ""
    return f"![{escaped_alt}](<{source}>{title_part})"

