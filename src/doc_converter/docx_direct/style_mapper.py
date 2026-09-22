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


def patch_document_xml(
    payload: bytes,
    analysis: DocumentAnalysis,
) -> tuple[bytes, dict[str, Any]]:
    """Patch mapped paragraph styles while preserving all other OOXML nodes."""

    root = parse_xml_payload(payload)
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("DOCX 的 word/document.xml 缺少 w:body。")
    paragraphs = {path: paragraph for paragraph, path, _ in _iter_paragraphs(body)}

    report: dict[str, Any] = {
        "mapped_count": 0,
        "uncertain_count": 0,
        "preserved_count": 0,
        "skipped_count": 0,
        "modified_element_ids": [],
        "formatting_removed": {},
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
        removed = clean_uniform_direct_formatting(paragraph)
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
