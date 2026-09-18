"""Deterministic Markdown normalization without model-assisted rewriting."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import yaml

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_LABEL_PATTERN = re.compile(r"^\s*(摘要|关键词)\s*[:：]\s*(.*)$")
_KEYWORD_SEPARATOR = re.compile(r"[；;，,\n]+")


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
    metadata = _normalize_metadata(raw_metadata)
    changes: list[dict[str, str | int]] = []
    extracted, consumed, extracted_changes = _extract_leading_metadata(
        content_lines,
        metadata,
        first_content_line,
    )
    metadata.update(extracted)
    changes.extend(extracted_changes)
    normalized_lines: list[str] = []

    for offset, line in enumerate(content_lines):
        if offset in consumed:
            continue
        source_line = first_content_line + offset
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

    body = "\n".join(normalized_lines).strip("\n")
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
) -> tuple[dict[str, Any], set[int], list[dict[str, str | int]]]:
    """Extract strongly labelled title-area blocks without rewriting ordinary prose."""

    barrier = _leading_metadata_barrier(lines)
    blocks = _non_empty_blocks(lines[:barrier])
    extracted: dict[str, Any] = {}
    consumed: set[int] = set()
    changes: list[dict[str, str | int]] = []
    subtitle_seen = False

    for block_start, block_end, block_lines in blocks:
        block_text = "\n".join(line.strip() for line in block_lines).strip()
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
                    "line": first_content_line + block_start,
                    "from": "labelled-paragraph",
                    "to": key,
                }
            )
            continue

        if (
            not subtitle_seen
            and "title" in metadata
            and "subtitle" not in metadata
            and "subtitle" not in extracted
            and _is_subtitle_candidate(block_lines)
        ):
            extracted["subtitle"] = block_text
            consumed.update(range(block_start, block_end))
            subtitle_seen = True
            changes.append(
                {
                    "line": first_content_line + block_start,
                    "from": "leading-paragraph",
                    "to": "document-subtitle",
                }
            )

    return extracted, consumed, changes


def _leading_metadata_barrier(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _HEADING_PATTERN.match(line) or stripped.startswith(("```", "~~~", "|")):
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
    if value.startswith(("- ", "* ", "+ ", "> ")) or re.match(r"^\d+[.)、]", value):
        return False
    return not value.endswith(("。", "！", "？", "；", ".", "!", "?", ";", ":", "："))


def _split_list_value(value: str) -> list[str]:
    return [item.strip() for item in _KEYWORD_SEPARATOR.split(value) if item.strip()]


def _integrity_inventory(source: str, normalized: str) -> dict[str, Any]:
    return {
        "images": _IMAGE_PATTERN.findall(source),
        "normalized_images": _IMAGE_PATTERN.findall(normalized),
        "links": _LINK_PATTERN.findall(source),
        "normalized_links": _LINK_PATTERN.findall(normalized),
    }
