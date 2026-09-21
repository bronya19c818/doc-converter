"""Deterministic Markdown normalization without model-assisted rewriting."""

from __future__ import annotations

import re
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
_LABEL_PATTERN = re.compile(r"^\s*(摘要|关键词)\s*[:：]\s*(.*)$")
_TITLE_AREA_LABEL_PATTERN = re.compile(
    r"^\s*(作者单位|作者|单位|机构|组织|部门|所属部门|日期|时间|发布时间)\s*[:：]\s*(.*)$"
)
_KEYWORD_SEPARATOR = re.compile(r"[；;，,\n]+")
_TABLE_CAPTION_PATTERN = re.compile(
    r"^\s*表\s*(?:\d+|[一二三四五六七八九十百千万]+)\s*(?:[：:、.．\s]|$)"
)
_NUMBERED_HEADING_PATTERN = re.compile(
    r"^#{1,6}\s+(?:[一二三四五六七八九十百千万]+[、.．)]|（[^）]+）|\d+[.、)])"
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
    confirmed_roles: dict[int, str],
) -> NormalizedDocument:
    """Normalize explicit and narrowly recognizable title-area metadata.

    ``confirmed_roles`` is keyed by the one-based source line number.  Leading
    subtitle and labelled abstract/keyword blocks are extracted only by the
    deterministic title-area rules below; other unconfirmed source text
    remains untouched so structural suggestions cannot become silent edits.
    """

    raw_metadata, content_lines, first_content_line = _extract_front_matter(source)
    preprocessed = preprocess_markdown(
        "\n".join(content_lines),
        line_map=[first_content_line + offset for offset in range(len(content_lines))],
    )
    content_lines = preprocessed.text.splitlines()
    metadata = _normalize_metadata(raw_metadata)
    changes: list[dict[str, str | int]] = list(preprocessed.changes)
    extracted, consumed, extracted_changes = _extract_leading_metadata(
        content_lines,
        metadata,
        first_content_line,
        line_numbers=preprocessed.line_map,
    )
    metadata.update(extracted)
    changes.extend(extracted_changes)
    normalized_lines: list[str] = []

    for offset, line in enumerate(content_lines):
        if offset in consumed:
            continue
        source_line = preprocessed.line_map[offset]
        match = _HEADING_PATTERN.match(line)
        confirmed_role = confirmed_roles.get(source_line)
        if match and confirmed_role in {"document-title", "document-subtitle"}:
            metadata["title" if confirmed_role == "document-title" else "subtitle"] = match.group(2)
            changes.append(
                {
                    "line": source_line,
                    "from": f"heading-{len(match.group(1))}",
                    "to": confirmed_role,
                }
            )
            continue
        normalized_lines.append(line)

    body = _normalize_html_tables("\n".join(normalized_lines).strip("\n"))
    markdown = _serialize_front_matter(metadata, body)
    integrity = _integrity_inventory(source, markdown)
    integrity["passed"] = integrity["images"] == integrity["normalized_images"] and integrity[
        "links"
    ] == integrity["normalized_links"]
    integrity.pop("normalized_images")
    integrity.pop("normalized_links")

    return NormalizedDocument(
        markdown=markdown,
        report={
            "schema": "normalized-md/v1",
            "source": filename,
            "changes": changes,
            "warnings": [],
            "metadata": metadata,
            "integrity": integrity,
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
                value = _split_list_value(value)
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


def _extract_leading_metadata(
    lines: list[str],
    metadata: dict[str, Any],
    first_content_line: int,
    *,
    line_numbers: list[int] | None = None,
) -> tuple[dict[str, Any], set[int], list[dict[str, str | int]]]:
    """Extract strongly labelled title-area blocks without rewriting ordinary prose."""

    barrier = _leading_metadata_barrier(lines)
    blocks = _non_empty_blocks(lines[:barrier])
    extracted: dict[str, Any] = {}
    consumed: set[int] = set()
    changes: list[dict[str, str | int]] = []
    subtitle_seen = False
    title_hint = bool(metadata.get("title"))

    for block_start, block_end, block_lines in blocks:
        block_text = "\n".join(line.strip() for line in block_lines).strip()
        heading_match = _HEADING_PATTERN.match(block_lines[0]) if len(block_lines) == 1 else None
        if heading_match:
            if _NUMBERED_HEADING_PATTERN.match(block_lines[0]):
                break
            heading_text = heading_match.group(2).strip()
            if (
                title_hint
                and "authors" not in metadata
                and "authors" not in extracted
                and _is_author_candidate(heading_text)
            ):
                extracted["authors"] = [heading_text]
                consumed.update(range(block_start, block_end))
                changes.append(
                    {
                        "line": _source_line_number(line_numbers, first_content_line, block_start),
                        "from": "heading-1",
                        "to": "authors",
                    }
                )
                continue
            title_hint = True
            continue

        label_match = _LABEL_PATTERN.match(block_text)
        if label_match:
            key = "abstract" if label_match.group(1) == "摘要" else "keywords"
            if key in metadata or key in extracted:
                continue
            value = label_match.group(2).strip()
            if len(block_lines) > 1:
                continuation = "\n".join(line.strip() for line in block_lines[1:]).strip()
                value = "\n".join(part for part in (value, continuation) if part)
            if key == "keywords":
                parsed = _split_list_value(value)
                if not parsed:
                    continue
                extracted[key] = parsed
            elif value:
                extracted[key] = value
            else:
                continue
            consumed.update(range(block_start, block_end))
            changes.append(
                {
                    "line": _source_line_number(line_numbers, first_content_line, block_start),
                    "from": "labelled-paragraph",
                    "to": key,
                }
            )
            continue

        title_area_match = _TITLE_AREA_LABEL_PATTERN.match(block_text)
        if title_area_match and title_hint:
            role, value = _metadata_label_value(title_area_match.group(1), title_area_match.group(2))
            if role and value and role not in metadata and role not in extracted:
                extracted[role] = _split_list_value(value) if role == "authors" else value
                consumed.update(range(block_start, block_end))
                changes.append(
                    {
                        "line": _source_line_number(line_numbers, first_content_line, block_start),
                        "from": "labelled-paragraph",
                        "to": role,
                    }
                )
                continue

        if title_hint and len(block_lines) == 1:
            role = _infer_title_area_role(block_text)
            if role is None and _is_date_candidate(block_text):
                role = "date"
            if role and role not in metadata and role not in extracted:
                extracted[role] = _split_list_value(block_text) if role == "authors" else block_text
                consumed.update(range(block_start, block_end))
                changes.append(
                    {
                        "line": _source_line_number(line_numbers, first_content_line, block_start),
                        "from": "leading-paragraph",
                        "to": role,
                    }
                )
                continue

        if (
            not subtitle_seen
            and title_hint
            and "subtitle" not in metadata
            and "subtitle" not in extracted
            and _is_subtitle_candidate(block_lines)
        ):
            extracted["subtitle"] = block_text
            consumed.update(range(block_start, block_end))
            subtitle_seen = True
            changes.append(
                {
                "line": _source_line_number(line_numbers, first_content_line, block_start),
                    "from": "leading-paragraph",
                    "to": "document-subtitle",
                }
            )
            continue

        # A non-metadata paragraph marks the end of the title area. This keeps
        # later short body paragraphs from being mistaken for authors or units.
        break

    return extracted, consumed, changes


def _source_line_number(line_numbers: list[int] | None, first_content_line: int, index: int) -> int:
    if line_numbers is not None and index < len(line_numbers):
        return line_numbers[index]
    return first_content_line + index


def _leading_metadata_barrier(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _NUMBERED_HEADING_PATTERN.match(line) or stripped.startswith(("```", "~~~", "|")):
            return index
    return len(lines)


def _non_empty_blocks(lines: list[str]) -> list[tuple[int, int, list[str]]]:
    blocks: list[tuple[int, int, list[str]]] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        start = index
        block_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            block_lines.append(lines[index])
            index += 1
        blocks.append((start, index, block_lines))
    return blocks


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


def _split_list_value(value: str) -> list[str]:
    return [item.strip() for item in _KEYWORD_SEPARATOR.split(value) if item.strip()]


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
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append("".join(self._cell).strip())
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
    output: list[str] = []
    in_fence = False
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence and "<table" in line.lower():
            block = [line]
            while "</table>" not in "\n".join(block).lower() and index + 1 < len(lines):
                index += 1
                block.append(lines[index])
            output.extend(_replace_html_table_block("\n".join(block)).splitlines())
        else:
            output.append(line)
        index += 1
    return "\n".join(output)


def _replace_html_table_block(block: str) -> str:
    parser = _HtmlTableParser()
    parser.feed(block)
    parser.close()
    if not parser.rows:
        return block
    width = max(len(row) for row in parser.rows)
    rows = [row + [""] * (width - len(row)) for row in parser.rows]
    escaped = [[cell.replace("|", "\\|") for cell in row] for row in rows]
    lines = ["| " + " | ".join(row) + " |" for row in escaped]
    lines.insert(1, "| " + " | ".join("---" for _ in range(width)) + " |")
    return "\n".join(lines)


def _integrity_inventory(source: str, normalized: str) -> dict[str, Any]:
    return {
        "images": _image_destinations(source),
        "normalized_images": _image_destinations(normalized),
        "links": _LINK_PATTERN.findall(source),
        "normalized_links": _LINK_PATTERN.findall(normalized),
    }


def _join_split_image_syntax(markdown: str) -> str:
    """Join exporter-style ``![alt]`` plus next-line ``(source)`` images."""

    lines = markdown.splitlines()
    output: list[str] = []
    fence: tuple[str, int] | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            output.append(line)
            index += 1
            continue

        label_match = _SPLIT_IMAGE_LABEL_LINE.fullmatch(line)
        if fence is None and label_match is not None and index + 1 < len(lines):
            destination_match = _SPLIT_IMAGE_DESTINATION_LINE.fullmatch(lines[index + 1])
            if destination_match is not None:
                output.append(label_match.group(1) + destination_match.group(1))
                index += 2
                continue
        output.append(line)
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
    fence: tuple[str, int] | None = None

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

    for line in markdown.splitlines(keepends=True):
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            flush_ordinary_lines()
            marker = fence_match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            output.append(line)
        elif fence is None:
            ordinary_lines.append(line)
        else:
            output.append(line)
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
