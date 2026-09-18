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


@dataclass(frozen=True)
class NormalizedDocument:
    """A normalized document and the audit data created while producing it."""

    markdown: str
    report: dict[str, Any]
    metadata: dict[str, Any]


_METADATA_KEYS = ("title", "subtitle", "organization", "department", "authors", "date")


def normalize_markdown(
    source: str,
    *,
    filename: str,
    confirmed_roles: dict[int, str],
) -> NormalizedDocument:
    """Move only user-confirmed document metadata out of Markdown blocks.

    ``confirmed_roles`` is keyed by the one-based source line number.  All
    unconfirmed source text remains untouched so that structural suggestions
    cannot become silent content edits.
    """

    raw_metadata, content_lines, first_content_line = _extract_front_matter(source)
    metadata = _normalize_metadata(raw_metadata)
    changes: list[dict[str, str | int]] = []
    normalized_lines: list[str] = []

    for offset, line in enumerate(content_lines):
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
        if key == "authors":
            if isinstance(value, str):
                value = [value]
            elif isinstance(value, tuple):
                value = list(value)
            elif not isinstance(value, list):
                value = []
            value = [str(author) for author in value if str(author).strip()]
        elif value is not None:
            value = str(value)
        normalized[key] = value
    for key, value in metadata.items():
        if key not in _METADATA_KEYS and key != "schema":
            normalized[key] = value
    return normalized


def _integrity_inventory(source: str, normalized: str) -> dict[str, Any]:
    return {
        "images": _IMAGE_PATTERN.findall(source),
        "normalized_images": _IMAGE_PATTERN.findall(normalized),
        "links": _LINK_PATTERN.findall(source),
        "normalized_links": _LINK_PATTERN.findall(normalized),
    }
