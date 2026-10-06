"""In-place paragraph style mapping for the direct DOCX route."""

from __future__ import annotations

from typing import Any

from docx.oxml.ns import qn

from doc_converter.docx_direct.analyzer import _iter_paragraphs
from doc_converter.docx_direct.character_styles import CharacterStyleProjector
from doc_converter.docx_direct.formatting import (
    apply_paragraph_policy,
    apply_run_policy,
    begin_policy_audit,
    protected_field_runs,
)
from doc_converter.docx_direct.model import DocumentAnalysis, PropertyDecision, TransformationAudit
from doc_converter.docx_direct.ooxml_patch import parse_xml_payload, serialize_xml_payload
from doc_converter.docx_direct.paragraph_styles import ParagraphStylePreserver
from doc_converter.docx_direct.transformation_policy import PRESERVE_POLICY, policy_for_role
from doc_converter.docx_styles import ROLE_TO_STYLE_ID

STYLE_CONTROLLED_RUN_TAGS = (qn("w:rFonts"), qn("w:sz"), qn("w:szCs"))


def patch_document_xml(
    payload: bytes,
    analysis: DocumentAnalysis,
    *,
    styles_payload: bytes | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Compatibility XML-only API; named-style rewrites need patch_document_parts."""
    neutral = _neutral_character_styles(styles_payload) if styles_payload is not None else {}
    return _patch_document_xml(
        payload,
        analysis,
        neutral_styles=neutral,
        paragraph_preserver=ParagraphStylePreserver(styles_payload) if styles_payload else None,
    )


def patch_document_parts(
    payload: bytes,
    analysis: DocumentAnalysis,
    *,
    styles_payload: bytes,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Atomically stage document XML and any policy-derived character styles."""
    projector = CharacterStyleProjector(styles_payload)
    document_xml, report = _patch_document_xml(
        payload,
        analysis,
        projector=projector,
        paragraph_preserver=ParagraphStylePreserver(styles_payload),
    )
    replacements = {"word/document.xml": document_xml}
    if projector.inserted_ids:
        replacements["word/styles.xml"] = projector.payload()
    report["projected_character_styles"] = list(projector.inserted_ids)
    return replacements, report


def _patch_document_xml(
    payload: bytes,
    analysis: DocumentAnalysis,
    *,
    projector: CharacterStyleProjector | None = None,
    neutral_styles: dict[str, frozenset[str]] | None = None,
    paragraph_preserver: ParagraphStylePreserver | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Apply role policies to existing nodes; recognition data stays untouched."""

    root = parse_xml_payload(payload)
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("DOCX 的 word/document.xml 缺少 w:body。")
    paragraphs = {path: paragraph for paragraph, path, _ in _iter_paragraphs(body)}
    field_runs = protected_field_runs(body)
    report: dict[str, Any] = {
        "mapped_count": 0,
        "uncertain_count": 0,
        "preserved_count": 0,
        "skipped_count": 0,
        "modified_element_ids": [],
        "formatting_removed": {},
        "table_indents_removed": 0,
        "paragraph_formatting_removed": {},
        "policy_counts": {},
    }
    for element in analysis.elements:
        paragraph = paragraphs.get(element.xml_path)
        decision = element.selected_decision
        if decision is None:
            raise ValueError(f"缺少 selected_decision：{element.element_id}")
        policy = policy_for_role(decision.role, action=decision.action)
        target_style = ROLE_TO_STYLE_ID.get(decision.role)
        if target_style is None:
            policy = PRESERVE_POLICY
        audit = (
            begin_policy_audit(paragraph, policy)
            if paragraph is not None
            else TransformationAudit(
                policy_name=PRESERVE_POLICY.name,
                policy_family=PRESERVE_POLICY.family,
                transform_safety="preserve",
            )
        )
        element.transformation = audit
        report["policy_counts"][audit.policy_family] = (
            report["policy_counts"].get(audit.policy_family, 0) + 1
        )
        if decision.action == "uncertain":
            report["uncertain_count"] += 1
            audit.skipped_properties.append(
                PropertyDecision(
                    property="paragraph",
                    level="paragraph",
                    mode="preserve",
                    reason="selected action 为 uncertain，保留原样",
                )
            )
            continue
        if decision.action != "mapped":
            report["preserved_count"] += 1
            audit.skipped_properties.append(
                PropertyDecision(
                    property="paragraph",
                    level="paragraph",
                    mode="preserve",
                    reason="selected action 非 mapped，保留原样",
                )
            )
            continue
        if target_style is None or paragraph is None or policy.family == "preserve":
            report["skipped_count"] += 1
            audit.skipped_properties.append(
                PropertyDecision(
                    property="paragraph",
                    level="paragraph",
                    mode="preserve",
                    reason="缺少角色策略、目标样式或源 XML 节点，无法安全映射",
                )
            )
            continue

        text_runs = [r for r in paragraph.iter(qn("w:r")) if any(n.text for n in r.iter(qn("w:t")))]
        if text_runs and all(r in field_runs for r in text_runs):
            audit.transform_safety = "preserve"
            audit.skipped_properties.append(
                PropertyDecision(
                    property="paragraph",
                    level="structure",
                    mode="preserve",
                    reason="整段文字属于复杂域结果，保留段落及字符格式以保护域结果",
                )
            )
            report["skipped_count"] += 1
            continue
        if paragraph_preserver is not None and not paragraph_preserver.preserve(
            paragraph, policy, audit
        ):
            report["skipped_count"] += 1
            continue
        paragraph_removed = apply_paragraph_policy(
            paragraph, policy, audit, target_style=target_style
        )
        if (
            decision.role in {"body-table", "table-row-header", "table-column-header"}
            and "ind" in paragraph_removed
        ):
            report["table_indents_removed"] += 1
        for property_name in paragraph_removed:
            report["paragraph_formatting_removed"][property_name] = (
                report["paragraph_formatting_removed"].get(property_name, 0) + 1
            )
        removed = apply_run_policy(
            paragraph,
            policy,
            audit,
            projector=projector,
            neutral_character_styles=neutral_styles,
            field_runs=field_runs,
        )
        for property_name, count in removed.items():
            report["formatting_removed"][property_name] = (
                report["formatting_removed"].get(property_name, 0) + count
            )
        report["mapped_count"] += 1
        report["modified_element_ids"].append(element.element_id)

    # No selected mapping may rewrite even an XML declaration or serialization whitespace.
    document_xml = serialize_xml_payload(root) if report["mapped_count"] else payload
    report["document_xml_changed"] = document_xml != payload
    return document_xml, report


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
