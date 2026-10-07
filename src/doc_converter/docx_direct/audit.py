"""JSON audit artifacts for direct DOCX normalization."""

from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

from doc_converter.docx_direct.model import DocumentAnalysis, NormalizationRecord
from doc_converter.docx_direct.role_capabilities import role_capabilities
from doc_converter.docx_styles import ROLE_TO_STYLE_ID
from doc_converter.style_library import StylePack

AUDIT_FILENAMES = (
    "docx-analysis.json",
    "docx-normalization-report.json",
    "style-pack.snapshot.json",
)
EVIDENCE_FIELDS = [
    "paragraph_properties",
    "run_properties",
    "effective_format",
    "signals",
]


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_normalization_records(analysis: DocumentAnalysis) -> list[NormalizationRecord]:
    records: list[NormalizationRecord] = []
    for element in analysis.elements:
        transformation = element.transformation
        decision = element.selected_decision
        if decision is None:
            raise ValueError(f"缺少 selected_decision：{element.element_id}")
        target_style = ROLE_TO_STYLE_ID.get(decision.role) if decision.action == "mapped" else None
        records.append(
            NormalizationRecord(
                element_id=element.element_id,
                text=element.text,
                original_style_id=element.original_style_id,
                original_style_name=element.original_style_name,
                detected_role=decision.role,
                confidence=decision.confidence,
                action=decision.action,
                target_style=target_style,
                reasons=decision.reasons or ["未匹配到可安全修改的规则，保留原样"],
                legacy_decision=element.legacy_decision,
                scored_decision=element.scored_decision,
                selected_decision=decision,
                selection_source=element.selection_source,
                selection_reason=element.selection_reason,
                policy_name=transformation.policy_name if transformation else None,
                policy_family=transformation.policy_family if transformation else None,
                transform_safety=transformation.transform_safety if transformation else None,
                removed_properties=transformation.removed_properties if transformation else [],
                preserved_properties=transformation.preserved_properties if transformation else [],
                skipped_properties=transformation.skipped_properties if transformation else [],
                inline_segments=element.inline_segments,
                **({key: getattr(transformation, key) for key in (
                    "expected_role_style", "style_application_status", "effective_style_after",
                    "effective_format_after", "effective_format_match", "format_checks",
                )} if transformation else {}),
            )
        )
    return records


def write_audit_bundle(
    audit_dir: Path,
    *,
    analysis: DocumentAnalysis,
    records: list[NormalizationRecord],
    style_pack: StylePack,
    source_sha256: str,
    output_sha256: str,
    source_unchanged: bool,
    style_report: dict[str, Any],
    patch_report: dict[str, Any],
) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    _write_json(audit_dir / "docx-analysis.json", _analysis_payload(analysis))

    def decision_counts(field: str) -> dict[str, int]:
        counts = Counter(
            d.action for e in analysis.elements if (d := getattr(e, field)) is not None
        )
        return {action: counts.get(action, 0) for action in ("mapped", "uncertain", "preserved")}

    def disagreements(first: str, second: str) -> int:
        return sum(
            (a.role, a.action) != (b.role, b.action)
            for e in analysis.elements
            if (a := getattr(e, first)) is not None and (b := getattr(e, second)) is not None
        )
    modified_parts: list[str] = []
    if style_report.get("inserted_count", 0) or style_report.get("replaced_count", 0) or patch_report.get("projected_character_styles"):
        modified_parts.append("word/styles.xml")
    if patch_report.get("document_xml_changed", False):
        modified_parts.append("word/document.xml")
    report = {
        "role_capabilities": role_capabilities(),
        "effective_format_verification": {
            "matched": sum(r.effective_format_match is True for r in records),
            "mismatched": sum(r.effective_format_match is False for r in records),
            "not_applied": sum(r.effective_format_match is None for r in records),
            "statuses": dict(Counter(r.style_application_status for r in records)),
        },
        "classification_mode": analysis.classification_mode,
        "scoring_config": analysis.scoring_config,
        "classification": {
            "legacy_counts": decision_counts("legacy_decision"),
            "scored_counts": decision_counts("scored_decision"),
            "selected_counts": decision_counts("selected_decision"),
            "legacy_scored_disagreements": disagreements("legacy_decision", "scored_decision"),
            "scored_selected_disagreements": disagreements("scored_decision", "selected_decision"),
        },
        "transformation_policy_counts": patch_report.get("policy_counts", {}),
        "shadow_comparison": {
            "compared": sum(e.scored_decision is not None for e in analysis.elements),
            "role_disagreements": sum(
                e.scored_decision is not None and e.scored_decision.role != e.role
                for e in analysis.elements
            ),
            "action_disagreements": sum(
                e.scored_decision is not None and e.scored_decision.action != e.action
                for e in analysis.elements
            ),
        },
        "source_sha256": source_sha256,
        "output_sha256": output_sha256,
        "source_unchanged": source_unchanged,
        "counts": {
            "mapped": patch_report.get("mapped_count", 0),
            "uncertain": patch_report.get("uncertain_count", 0),
            "preserved": patch_report.get("preserved_count", 0),
            "skipped": patch_report.get("skipped_count", 0),
        },
        "modified_xml_parts": modified_parts,
        "style_injection": style_report,
        "xml_patch": patch_report,
        "elements": [record.model_dump(mode="json") for record in records],
    }
    _write_json(audit_dir / "docx-normalization-report.json", report)
    _write_json(audit_dir / "style-pack.snapshot.json", style_pack.model_dump(mode="json"))


def _analysis_payload(analysis: DocumentAnalysis) -> dict[str, Any]:
    """Serialize direct evidence, resolved evidence, and classification separately."""

    payload = analysis.model_dump(mode="json")
    payload["evidence_fields"] = list(EVIDENCE_FIELDS)
    for element in payload.get("elements", []):
        for field in EVIDENCE_FIELDS:
            element.setdefault(field, {})
        for field in ("role", "confidence", "action", "reasons"):
            element.setdefault(field, None)
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
