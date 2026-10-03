"""Remove source formatting that would override mapped paragraph styles."""

from __future__ import annotations

from typing import Any

from docx.oxml.ns import qn

TEXT_TAGS = {qn("w:t"), qn("w:delText")}
DIRECT_PROPERTY_TAGS = (
    qn("w:color"),
    qn("w:b"),
    qn("w:bCs"),
    qn("w:i"),
    qn("w:iCs"),
)
STYLE_CONTROLLED_RUN_TAGS = (qn("w:rFonts"), qn("w:sz"), qn("w:szCs"))


def clean_uniform_direct_formatting(
    paragraph: Any, *, neutral_character_styles: dict[str, frozenset[str]] | None = None
) -> dict[str, int]:
    """Apply mapped font and size; retain nonuniform local emphasis."""

    runs = [run for run in paragraph.iter(qn("w:r")) if _contains_text(run)]
    if not runs:
        return {}

    removed: dict[str, int] = {}
    neutral_character_styles = neutral_character_styles or {}
    for property_tag in STYLE_CONTROLLED_RUN_TAGS:
        count = 0
        for run in runs:
            if not _character_style_is_neutral(
                run, neutral_character_styles.get(_local_name(property_tag), frozenset())
            ):
                continue
            properties = run.find(qn("w:rPr"))
            node = properties.find(property_tag) if properties is not None else None
            if node is not None:
                properties.remove(node)
                count += 1
        if count:
            removed[_local_name(property_tag)] = count

    for property_tag in DIRECT_PROPERTY_TAGS:
        property_nodes = [_property_node(run, property_tag) for run in runs]
        complete_match = all(node is not None for node in property_nodes) and len(
            {_node_signature(node) for node in property_nodes if node is not None}
        ) == 1
        if not complete_match:
            continue
        removed_count = 0
        for run in runs:
            properties = run.find(qn("w:rPr"))
            if properties is not None:
                node = properties.find(property_tag)
                if node is not None:
                    properties.remove(node)
                    removed_count += 1
        removed[_local_name(property_tag)] = removed_count
    return removed


def _contains_text(run: Any) -> bool:
    return any(node.tag in TEXT_TAGS and bool(node.text) for node in run.iter())


def _property_node(run: Any, property_tag: str) -> Any | None:
    properties = run.find(qn("w:rPr"))
    return properties.find(property_tag) if properties is not None else None


def _node_signature(node: Any) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((_local_name(key), str(value)) for key, value in node.attrib.items()))


def _character_style_is_neutral(run: Any, neutral_styles: frozenset[str]) -> bool:
    style = _property_node(run, qn("w:rStyle"))
    return style is None or style.get(qn("w:val")) in neutral_styles


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
