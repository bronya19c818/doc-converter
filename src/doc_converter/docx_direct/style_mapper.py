"""In-place paragraph style mapping for the direct DOCX route."""

from __future__ import annotations

from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from doc_converter.docx_direct.analyzer import _iter_paragraphs
from doc_converter.docx_direct.formatting import clean_uniform_direct_formatting
from doc_converter.docx_direct.model import DocumentAnalysis
from doc_converter.docx_direct.ooxml_patch import parse_xml_payload, serialize_xml_payload
from doc_converter.docx_styles import ROLE_TO_STYLE_ID

STYLE_CONTROLLED_PARAGRAPH_TAGS = (qn("w:ind"), qn("w:jc"), qn("w:spacing"))
STYLE_CONTROLLED_RUN_TAGS = (qn("w:rFonts"), qn("w:sz"), qn("w:szCs"))


def patch_document_xml(
    payload: bytes,
    analysis: DocumentAnalysis,
    *,
    styles_payload: bytes | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Patch mapped paragraph styles while preserving all other OOXML nodes."""

    root = parse_xml_payload(payload)
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("DOCX 的 word/document.xml 缺少 w:body。")
    paragraphs = {path: paragraph for paragraph, path, _ in _iter_paragraphs(body)}
    neutral_styles = (
        _neutral_character_styles(styles_payload) if styles_payload is not None else {}
    )

    report: dict[str, Any] = {
        "mapped_count": 0,
        "uncertain_count": 0,
        "preserved_count": 0,
        "skipped_count": 0,
        "modified_element_ids": [],
        "formatting_removed": {},
        "table_indents_removed": 0,
        "paragraph_formatting_removed": {},
    }
    for element in analysis.elements:
        if element.action == "uncertain":
            report["uncertain_count"] += 1
            continue
        if element.action != "mapped":
            report["preserved_count"] += 1
            continue

        target_style = ROLE_TO_STYLE_ID.get(element.role)
        paragraph = paragraphs.get(element.xml_path)
        if target_style is None or paragraph is None:
            report["skipped_count"] += 1
            continue

        _set_paragraph_style(paragraph, target_style)
        paragraph_removed = _clear_paragraph_style_overrides(paragraph)
        if element.role in {"body-table", "table-row-header", "table-column-header"} and "ind" in paragraph_removed:
            report["table_indents_removed"] += 1
        for property_name in paragraph_removed:
            report["paragraph_formatting_removed"][property_name] = (
                report["paragraph_formatting_removed"].get(property_name, 0) + 1
            )
        removed = clean_uniform_direct_formatting(
            paragraph, neutral_character_styles=neutral_styles
        )
        for property_name, count in removed.items():
            report["formatting_removed"][property_name] = (
                report["formatting_removed"].get(property_name, 0) + count
            )
        report["mapped_count"] += 1
        report["modified_element_ids"].append(element.element_id)

    return serialize_xml_payload(root), report


def _set_paragraph_style(paragraph: Any, style_id: str) -> None:
    properties = paragraph.find(qn("w:pPr"))
    if properties is None:
        properties = OxmlElement("w:pPr")
        paragraph.insert(0, properties)
    style = properties.find(qn("w:pStyle"))
    if style is None:
        style = OxmlElement("w:pStyle")
        properties.insert(0, style)
    style.set(qn("w:val"), style_id)


def _clear_paragraph_style_overrides(paragraph: Any) -> set[str]:
    properties = paragraph.find(qn("w:pPr"))
    if properties is None:
        return set()
    removed = set()
    for tag in STYLE_CONTROLLED_PARAGRAPH_TAGS:
        if tag == qn("w:ind") and properties.find(qn("w:numPr")) is not None:
            continue
        node = properties.find(tag)
        if node is not None:
            properties.remove(node)
            removed.add(tag.rsplit("}", 1)[-1])
    return removed


def _neutral_character_styles(payload: bytes) -> dict[str, frozenset[str]]:
    root = parse_xml_payload(payload)
    styles = {
        style_id: style
        for style in root.findall(qn("w:style"))
        if style.get(qn("w:type")) == "character"
        and (style_id := style.get(qn("w:styleId"))) is not None
    }

    def is_neutral(style_id: str, property_tag: str, visited: frozenset[str]) -> bool:
        style = styles.get(style_id)
        if style is None or style_id in visited:
            return False
        properties = style.find(qn("w:rPr"))
        if properties is not None and properties.find(property_tag) is not None:
            return False
        parent = style.find(qn("w:basedOn"))
        return parent is None or is_neutral(
            parent.get(qn("w:val"), ""), property_tag, visited | {style_id}
        )

    return {
        tag.rsplit("}", 1)[-1]: frozenset(
            style_id for style_id in styles if is_neutral(style_id, tag, frozenset())
        )
        for tag in STYLE_CONTROLLED_RUN_TAGS
    }
