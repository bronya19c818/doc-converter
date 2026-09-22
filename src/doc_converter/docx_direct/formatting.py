"""Conservative cleanup of direct run formatting after style mapping."""

from __future__ import annotations

from typing import Any

from docx.oxml.ns import qn

TEXT_TAGS = {qn("w:t"), qn("w:delText")}
DIRECT_PROPERTY_TAGS = (
    qn("w:rFonts"),
    qn("w:sz"),
    qn("w:szCs"),
    qn("w:color"),
    qn("w:b"),
    qn("w:bCs"),
    qn("w:i"),
    qn("w:iCs"),
)


def clean_uniform_direct_formatting(paragraph: Any) -> dict[str, int]:
    """Remove allowed direct properties only when every text run agrees."""

    runs = [run for run in paragraph.iter(qn("w:r")) if _contains_text(run)]
    if not runs:
        return {}

    removed: dict[str, int] = {}
    for property_tag in DIRECT_PROPERTY_TAGS:
        property_nodes = [_property_node(run, property_tag) for run in runs]
        if any(node is None for node in property_nodes):
            continue
        signatures = {_node_signature(node) for node in property_nodes if node is not None}
        if len(signatures) != 1:
            continue
        for run in runs:
            properties = run.find(qn("w:rPr"))
            if properties is not None:
                node = properties.find(property_tag)
                if node is not None:
                    properties.remove(node)
        removed[_local_name(property_tag)] = len(runs)
    return removed


def _contains_text(run: Any) -> bool:
    return any(node.tag in TEXT_TAGS and bool(node.text) for node in run.iter())


def _property_node(run: Any, property_tag: str) -> Any | None:
    properties = run.find(qn("w:rPr"))
    return properties.find(property_tag) if properties is not None else None


def _node_signature(node: Any) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((_local_name(key), str(value)) for key, value in node.attrib.items()))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
