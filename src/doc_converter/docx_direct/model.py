"""Serializable models shared by the direct DOCX normalization pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

Action = Literal["mapped", "uncertain", "preserved"]
DocumentRegion = Literal["preface", "body", "postface"]


class ElementAnalysis(BaseModel):
    """Read-only evidence and classification for one document paragraph."""

    element_id: str
    element_type: Literal["paragraph"]
    text: str
    document_order: int
    xml_path: tuple[int, ...]
    region: DocumentRegion
    original_style_id: str | None = None
    original_style_name: str | None = None
    paragraph_properties: dict[str, Any] = Field(default_factory=dict)
    run_properties: list[dict[str, Any]] = Field(default_factory=list)
    numbering_properties: dict[str, Any] = Field(default_factory=dict)
    table_context: dict[str, Any] | None = None
    has_hyperlink: bool = False
    has_tab: bool = False
    has_manual_break: bool = False
    has_drawing: bool = False
    has_field: bool = False
    role: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    action: Action = "preserved"
    reasons: list[str] = Field(default_factory=list)


class DocumentAnalysis(BaseModel):
    """The complete analysis of one source DOCX package."""

    source_sha256: str
    elements: list[ElementAnalysis] = Field(default_factory=list)
    package_entries: list[str] = Field(default_factory=list)
    main_document_stats: dict[str, int] = Field(default_factory=dict)


class NormalizationRecord(BaseModel):
    """Auditable decision and result for one analyzed element."""

    element_id: str
    text: str
    original_style_id: str | None = None
    original_style_name: str | None = None
    detected_role: str
    confidence: float = Field(ge=0.0, le=1.0)
    action: Action
    target_style: str | None = None
    reasons: list[str] = Field(default_factory=list)


class DirectNormalizeResult(BaseModel):
    """Paths and analysis returned after a successful direct normalization."""

    output_path: Path
    analysis_path: Path
    normalization_report_path: Path
    style_pack_snapshot_path: Path
    analysis: DocumentAnalysis
    records: list[NormalizationRecord] = Field(default_factory=list)
