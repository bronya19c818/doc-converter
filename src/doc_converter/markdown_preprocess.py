"""Deterministic second-pass cleanup for Markdown produced by OCR/exporters.

The converter receives Markdown from several local sources.  Those sources
often flatten every heading to ``#`` and leave page headers, tables of
contents, or cross-page fragments in the text.  This module deliberately
contains only local, explainable transformations; it does not infer content
with a model and never changes wording beyond joining an obvious fragment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CN_NUM = "一二三四五六七八九十百千万零〇"
_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")
_TOC_HEADING_PATTERN = re.compile(r"^#{0,6}\s*目\s*次\s*$")
_STANDARD_CODE_PATTERN = re.compile(
    r"^(?:Q/GDW|GB/T|GB|DL/T|NB/T|JB/T|HG/T|T/[A-Za-z0-9._-]+|Q/[A-Za-z0-9._-]+)"
    r"\s*[\d.]+\s*[—\-–]\s*\d{4}$",
    re.IGNORECASE,
)
_CHAPTER_HEADING_PATTERN = re.compile(
    rf"^(?:第\s*[{_CN_NUM}\d]+\s*[章篇]|[{_CN_NUM}]+\s*[、.．])"
)
_CHINESE_BRACKET_HEADING_PATTERN = re.compile(
    rf"^[（(]\s*[{_CN_NUM}]+\s*[）)]"
)
_ARABIC_BRACKET_HEADING_PATTERN = re.compile(r"^[（(]\s*\d+\s*[）)]")
_DECIMAL_HEADING_PATTERN = re.compile(r"^(\d+(?:\s*\.\s*\d+)+)(?=\s|[、.．)])")
_ARABIC_HEADING_PATTERN = re.compile(r"^\d+(?:\s*[、.．)])(?=\s|\S)")
_LETTER_HEADING_PATTERN = re.compile(r"^[A-Za-zＡ-Ｚａ-ｚ][、.．)](?=\s|\S)")
_STANDARD_ROOT_HEADING_PATTERN = re.compile(r"^\d+(?=\s+\S)")
_BARE_DECIMAL_HEADING_PATTERN = re.compile(r"^(\d+(?:\s*\.\s*\d+)+)\s+(\S.*)$")
_TITLE_AREA_LABEL_PATTERN = re.compile(
    r"^(?:摘要|关键词|作者(?:单位)?|单位|机构|组织|部门|日期|时间|发布时间)\s*[:：]"
)


@dataclass(frozen=True)
class MarkdownPreprocessResult:
    """The transformed Markdown and an audit-friendly list of actions."""

    text: str
    changes: list[dict[str, str | int]]
    line_map: list[int]


def preprocess_markdown(
    markdown: str,
    *,
    line_map: list[int] | None = None,
) -> MarkdownPreprocessResult:
    """Apply the safe subset of the former Dify Markdown cleanup pipeline."""

    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    mapped_lines = list(line_map or range(1, len(lines) + 1))
    if len(mapped_lines) != len(lines):
        raise ValueError("Markdown 行号映射必须与输入行数一致。")
    changes: list[dict[str, str | int]] = []

    lines, mapped_lines, removed_toc = _remove_toc_lines(lines, mapped_lines)
    if removed_toc:
        changes.append({"to": "remove-toc", "count": removed_toc})

    lines, mapped_lines, removed_codes = _remove_duplicate_standard_code_lines(
        lines,
        mapped_lines,
    )
    if removed_codes:
        changes.append({"to": "remove-duplicate-standard-code", "count": removed_codes})

    lines, mapped_lines, repaired = _repair_broken_paragraph_lines(lines, mapped_lines)
    if repaired:
        changes.append({"to": "repair-broken-paragraph", "count": repaired})

    text = "\n".join(lines)
    standard_document = _looks_like_technical_standard(text)
    lines, mapped_lines, bare_heading_changes = _normalize_standard_subheading_lines(
        lines,
        mapped_lines,
        standard_document,
    )
    changes.extend(bare_heading_changes)
    lines, mapped_lines, heading_changes = _normalize_heading_lines(
        lines,
        mapped_lines,
        standard_document=standard_document,
    )
    changes.extend(heading_changes)
    while lines and not lines[0].strip():
        lines.pop(0)
        mapped_lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
        mapped_lines.pop()
    return MarkdownPreprocessResult(
        text="\n".join(lines),
        changes=changes,
        line_map=mapped_lines,
    )


def is_standard_code_line(text: str) -> bool:
    """Return whether a standalone line looks like a Chinese standard code."""

    candidate = text.strip()
    return len(candidate) <= 80 and _STANDARD_CODE_PATTERN.fullmatch(candidate) is not None


def remove_duplicate_standard_codes(text: str) -> tuple[str, int]:
    """Keep the first repeated standard code and remove later page-header copies."""

    lines = text.splitlines()
    output, _, removed = _remove_duplicate_standard_code_lines(lines, list(range(1, len(lines) + 1)))
    return "\n".join(output), removed


def _remove_duplicate_standard_code_lines(
    lines: list[str],
    line_map: list[int],
) -> tuple[list[str], list[int], int]:
    seen: set[str] = set()
    removed = 0
    output: list[str] = []
    output_map: list[int] = []
    in_fence = False
    for line, source_line in zip(lines, line_map, strict=True):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence and is_standard_code_line(line):
            key = re.sub(r"\s+", "", line).upper()
            if key in seen:
                output.append("")
                output_map.append(source_line)
                removed += 1
                continue
            seen.add(key)
        output.append(line)
        output_map.append(source_line)
    return output, output_map, removed


def remove_toc_sections(text: str) -> tuple[str, int]:
    """Remove a Markdown ``目次`` block up to the next heading."""

    lines = text.splitlines()
    output, _, removed = _remove_toc_lines(lines, list(range(1, len(lines) + 1)))
    return "\n".join(output), removed


def _remove_toc_lines(
    lines: list[str],
    line_map: list[int],
) -> tuple[list[str], list[int], int]:
    output: list[str] = []
    output_map: list[int] = []
    skipping = False
    removed = 0
    in_fence = False
    for index, (line, source_line) in enumerate(zip(lines, line_map, strict=True)):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            if skipping:
                skipping = False
            in_fence = not in_fence
            output.append(line)
            output_map.append(source_line)
            continue
        if not in_fence and _TOC_HEADING_PATTERN.fullmatch(stripped):
            if not _has_following_heading(lines, index):
                output.append(line)
                output_map.append(source_line)
                continue
            skipping = True
            removed += 1
            continue
        if skipping:
            if re.match(r"^#{1,6}\s+\S", stripped):
                skipping = False
                output.append(line)
                output_map.append(source_line)
            else:
                removed += 1
            continue
        output.append(line)
        output_map.append(source_line)
    return output, output_map, removed


def _has_following_heading(lines: list[str], start: int) -> bool:
    in_fence = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if not in_fence and re.match(r"^#{1,6}\s+\S", stripped):
            return True
    return False


def repair_broken_paragraphs(text: str) -> tuple[str, int]:
    """Join only clear cross-page fragments, retaining ordinary paragraphs."""

    lines = text.splitlines()
    output, _, repaired = _repair_broken_paragraph_lines(lines, list(range(1, len(lines) + 1)))
    return "\n".join(output), repaired


def _repair_broken_paragraph_lines(
    lines: list[str],
    line_map: list[int],
) -> tuple[list[str], list[int], int]:
    blocks: list[tuple[str, list[int]]] = []
    current_lines: list[str] = []
    current_map: list[int] = []

    def flush() -> None:
        if current_lines and any(item.strip() for item in current_lines):
            blocks.append(("\n".join(current_lines).strip(), current_map.copy()))
        current_lines.clear()
        current_map.clear()

    for line, source_line in zip(lines, line_map, strict=True):
        if line.strip():
            current_lines.append(line)
            current_map.append(source_line)
        else:
            flush()
    flush()

    result: list[tuple[str, list[int]]] = []
    repaired = 0
    for part, part_map in blocks:
        if result and _should_merge_fragment(result[-1][0], part):
            previous, previous_map = result[-1]
            result[-1] = (
                previous.rstrip() + part.lstrip(),
                previous_map[:-1] + [previous_map[-1]] + part_map[1:],
            )
            repaired += 1
        else:
            result.append((part, part_map))

    output: list[str] = []
    output_map: list[int] = []
    for index, (part, part_map) in enumerate(result):
        if index:
            output.append("")
            output_map.append(part_map[0])
        part_lines = part.splitlines() or [part]
        output.extend(part_lines)
        output_map.extend(part_map[: len(part_lines)] or [part_map[0]] * len(part_lines))
    return output, output_map, repaired


def _should_merge_fragment(previous: str, current: str) -> bool:
    previous = previous.strip()
    current = current.strip()
    if not previous or not current or _is_structural_start(current):
        return False
    if previous.startswith(("#", "|", "```", "~~~")):
        return False
    if re.search(r"[。！？.!?]$", previous):
        return False
    if len(current) <= 8 and re.search(r"[。！？；，、.!?;,]$", current):
        return True
    if re.search(r"[，,、；;：:]$", previous):
        return True
    if _has_unclosed_pair(previous):
        return True
    if re.match(r"^[\u4e00-\u9fff]{1,2}[，、；：:]", current) and len(previous) >= 8:
        return True
    return False


def _is_structural_start(value: str) -> bool:
    first = value.strip()
    if first.startswith(("#", "|", "```", "~~~")) or _TITLE_AREA_LABEL_PATTERN.match(first):
        return True
    return bool(
        re.match(
            rf"^(?:第[{_CN_NUM}\d]+[条章节]|[{_CN_NUM}]+[、．.]|[（(][{_CN_NUM}\d]+[）)]|"
            rf"\d+(?:\.\d+)*\s*[|、．)]|附件(?:\s*[：:]|\s*\d)|附\s*录\s*[A-Za-zＡ-Ｚａ-ｚ\d{_CN_NUM}])",
            first,
        )
    )


def _has_unclosed_pair(value: str) -> bool:
    return any(
        value.count(left) > value.count(right)
        for left, right in (("《", "》"), ("“", "”"), ("（", "）"), ("(", ")"), ("【", "】"))
    )


def normalize_standard_subheadings(
    text: str,
    standard_document: bool,
) -> tuple[str, list[dict[str, str | int]]]:
    """Turn safe bare numeric standard subheadings into Markdown headings."""

    lines = text.splitlines()
    output, _, changes = _normalize_standard_subheading_lines(
        lines,
        list(range(1, len(lines) + 1)),
        standard_document,
    )
    return "\n".join(output), changes


def _normalize_standard_subheading_lines(
    lines: list[str],
    line_map: list[int],
    standard_document: bool,
) -> tuple[list[str], list[int], list[dict[str, str | int]]]:
    if not standard_document:
        return lines, line_map, []

    changes: list[dict[str, str | int]] = []
    output: list[str] = []
    output_map: list[int] = []
    in_fence = False
    for line, source_line in zip(lines, line_map, strict=True):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
        if in_fence:
            output.append(line)
            output_map.append(source_line)
            continue
        match = _BARE_DECIMAL_HEADING_PATTERN.match(stripped)
        if match is None or not _looks_like_standard_heading_text(match.group(2)):
            output.append(line)
            output_map.append(source_line)
            continue
        number = re.sub(r"\s*\.\s*", ".", match.group(1))
        level = min(6, number.count(".") + 2)
        output.append(f"{'#' * level} {number} {match.group(2).strip()}")
        output_map.append(source_line)
        changes.append(
            {
                "line": source_line,
                "from": "paragraph",
                "to": "heading-level",
                "level": level,
                "reason": "按技术标准编号识别裸标题",
            }
        )
    return output, output_map, changes


def normalize_heading_levels(
    text: str,
    *,
    standard_document: bool = False,
) -> tuple[str, list[dict[str, str | int]]]:
    """Rebuild flattened ATX heading levels from common Chinese numbering."""

    lines = text.splitlines()
    output, _, changes = _normalize_heading_lines(
        lines,
        list(range(1, len(lines) + 1)),
        standard_document=standard_document,
    )
    return "\n".join(output), changes


def _normalize_heading_lines(
    lines: list[str],
    line_map: list[int],
    *,
    standard_document: bool,
) -> tuple[list[str], list[int], list[dict[str, str | int]]]:
    output: list[str] = []
    output_map: list[int] = []
    active_levels: dict[int, str] = {}
    child_levels: dict[tuple[str, int, str], int] = {}
    changes: list[dict[str, str | int]] = []
    in_fence = False

    for line, source_line in zip(lines, line_map, strict=True):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            output.append(line)
            output_map.append(source_line)
            continue
        if in_fence:
            output.append(line)
            output_map.append(source_line)
            continue

        match = _HEADING_PATTERN.match(line)
        if match is None:
            output.append(line)
            output_map.append(source_line)
            continue

        current_level = len(match.group(1))
        title = match.group(2).strip()
        target_level = _heading_level_for_title(
            title,
            active_levels,
            current_level,
            child_levels,
            standard_document=standard_document,
        )
        if target_level != current_level:
            line = f"{'#' * target_level} {title}"
            changes.append(
                {
                    "line": source_line,
                    "from": f"heading-{current_level}",
                    "to": "heading-level",
                    "level": target_level,
                    "reason": "按中文/数字编号重建标题层级",
                }
            )
        output.append(line)
        output_map.append(source_line)
        for level in list(active_levels):
            if level >= target_level:
                del active_levels[level]
        active_levels[target_level] = title

    return output, output_map, changes


def _heading_level_for_title(
    title: str,
    active_levels: dict[int, str],
    current_level: int,
    child_levels: dict[tuple[str, int, str], int],
    *,
    standard_document: bool,
) -> int:
    kind = _heading_kind(title, standard_document=standard_document)
    if kind == "standard-root":
        return 2
    if kind == "chapter":
        return 1
    if kind == "cn-bracket":
        return 2
    if kind == "decimal":
        decimal_match = _DECIMAL_HEADING_PATTERN.match(title)
        assert decimal_match is not None
        return min(6, decimal_match.group(1).count(".") + 2)
    if kind in {"arabic-bracket", "arabic", "letter"}:
        parent_level = max(
            (
                level
                for level, parent_title in active_levels.items()
                if _heading_kind(parent_title, standard_document=standard_document) != kind
            ),
            default=0,
        )
        parent_title = active_levels.get(parent_level, "")
        context_key = (kind, parent_level, parent_title)
        if context_key not in child_levels:
            child_levels[context_key] = min(6, max(1, parent_level + 1))
        return child_levels[context_key]
    # An unnumbered ATX heading already carries an explicit hierarchy.  Keep
    # that level instead of flattening it to the deepest numbered heading.
    return current_level


def _heading_kind(title: str, *, standard_document: bool) -> str | None:
    if standard_document and _STANDARD_ROOT_HEADING_PATTERN.match(title):
        return "standard-root"
    if _CHAPTER_HEADING_PATTERN.match(title):
        return "chapter"
    if _CHINESE_BRACKET_HEADING_PATTERN.match(title):
        return "cn-bracket"
    if _ARABIC_BRACKET_HEADING_PATTERN.match(title):
        return "arabic-bracket"
    if _DECIMAL_HEADING_PATTERN.match(title):
        return "decimal"
    if _ARABIC_HEADING_PATTERN.match(title):
        return "arabic"
    if _LETTER_HEADING_PATTERN.match(title):
        return "letter"
    return None


def _looks_like_technical_standard(text: str) -> bool:
    if any(is_standard_code_line(line) for line in text.splitlines()):
        return True
    return bool(
        re.search(r"^#{1,6}\s*1\s+范围\s*$", text, re.MULTILINE)
        and re.search(r"^#{1,6}\s*2\s+规范性引用文件\s*$", text, re.MULTILINE)
    )


def _looks_like_standard_heading_text(title: str) -> bool:
    title = title.strip()
    if not title or len(title) > 42 or "|" in title or "$" in title:
        return False
    if re.search(r"[。；;！？!?：:]$", title):
        return False
    return not any(
        marker in title
        for marker in (
            "应",
            "宜",
            "不得",
            "不应",
            "应当",
            "需要",
            "负责",
            "按照",
            "依据",
            "采用",
            "进行",
            "设置",
            "建立",
            "开展",
            "符合",
            "保证",
            "确保",
            "可以",
            "可根据",
            "由",
            "将",
        )
    )
