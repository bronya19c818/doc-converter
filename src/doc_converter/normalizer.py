"""Deterministic Markdown normalization without model-assisted rewriting."""

from __future__ import annotations

import re
from dataclasses import dataclass
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

    metadata, content_lines, first_content_line = _extract_front_matter(source)
    metadata["schema"] = "normalized-md/v1"
    changes: list[dict[str, str | int]] = []
    normalized_lines: list[str] = []

    for offset, line in enumerate(content_lines):
        source_line = first_content_line + offset
        match = _HEADING_PATTERN.match(line)
        confirmed_role = confirmed_roles.get(source_line)
        if match and confirmed_role == "document-title":
            metadata["title"] = match.group(2)
            changes.append(
                {"line": source_line, "from": f"heading-{len(match.group(1))}", "to": "document-title"}
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
            "integrity": integrity,
        },
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
    serialized_metadata = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{serialized_metadata}\n---\n\n{body}\n"


def _integrity_inventory(source: str, normalized: str) -> dict[str, Any]:
    return {
        "images": _IMAGE_PATTERN.findall(source),
        "normalized_images": _IMAGE_PATTERN.findall(normalized),
        "links": _LINK_PATTERN.findall(source),
        "normalized_links": _LINK_PATTERN.findall(normalized),
    }
