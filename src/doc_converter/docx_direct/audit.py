"""JSON audit artifacts for direct DOCX normalization."""

from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

from doc_converter.docx_direct.model import DocumentAnalysis, NormalizationRecord
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
        target_style = ROLE_TO_STYLE_ID.get(element.role) if element.action == "mapped" else None
        records.append(
            NormalizationRecord(
                element_id=element.element_id,
                text=element.text,
                original_style_id=element.original_style_id,
                original_style_name=element.original_style_name,
                detected_role=element.role,
                confidence=element.confidence,
                action=element.action,
                target_style=target_style,
                reasons=element.reasons or ["未匹配到可安全修改的规则，保留原样"],
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

    counts = Counter(record.action for record in records)
    modified_parts: list[str] = []
    if style_report.get("inserted_count", 0):
        modified_parts.append("word/styles.xml")
    if patch_report.get("mapped_count", 0):
        modified_parts.append("word/document.xml")
    report = {
        "source_sha256": source_sha256,
        "output_sha256": output_sha256,
        "source_unchanged": source_unchanged,
        "counts": {
            "mapped": counts.get("mapped", 0),
            "uncertain": counts.get("uncertain", 0),
            "preserved": counts.get("preserved", 0),
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
