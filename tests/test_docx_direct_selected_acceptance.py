"""End-to-end tests written before selected-decision implementation.

Failures caught: missing selection, legacy takeover, ground-truth errors,
incorrect target styles/statistics, unsafe edits and ZIP/text/structure loss.
Every API conversion leaves downloadable DOCX, audit and verification.json.
"""

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document

import doc_converter.docx_direct.style_mapper as mapper
from doc_converter.docx_direct.normalizer import normalize_docx_direct
from doc_converter.docx_direct.scoring import ScoringConfig
from doc_converter.docx_direct.transformation_policy import PRESERVE_POLICY
from doc_converter.style_library import create_style_pack
from scripts.verify_docx_selected import FIXTURES, PRESSURE, verify_sample

TRUTH = json.loads((FIXTURES / "ground_truth.json").read_text(encoding="utf-8"))["files"]


@pytest.mark.parametrize("name", list(TRUTH))
def test_selected_decision_matches_acceptance_ground_truth(name, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DOC_CONVERTER_LIBREOFFICE", str(tmp_path / "no-preview"))
    verify_sample(FIXTURES / name, tmp_path / Path(name).stem, TRUTH[name])


@pytest.mark.parametrize("mode", ["legacy", "shadow", "hybrid", "scored"])
def test_decision_modes_preserve_pressure_document(mode, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DOC_CONVERTER_LIBREOFFICE", str(tmp_path / "no-preview"))
    verify_sample(PRESSURE, tmp_path / mode, [], mode)


@pytest.mark.parametrize("config,marker,role,action,selection", [
    ({}, "1. 盘点范围", "heading-2", "mapped", "scored"),
    ({"high_score": 250}, "1. 盘点范围", "heading-2", "preserved", "preserve"),
    ({"high_score": 250}, "一、总体要求", "heading-1", "uncertain", "agreement"),
    ({"ambiguous_margin": 100, "high_margin": 100},
     "一、总体要求", "unknown", "preserved", "preserve"),
    ({"medium_score": 400, "high_score": 500},
     "一、总体要求", "unknown", "preserved", "preserve"),
])
def test_hybrid_boundaries_through_full_conversion(
    config, marker, role, action, selection, tmp_path,
) -> None:
    result = normalize_docx_direct(
        FIXTURES / "sample_03_ambiguous_numbering.docx",
        create_style_pack(name="阈值边界验收", format_id="docx"),
        tmp_path / "normalized.docx", scoring_config=ScoringConfig(**config),
    )
    e = next(e for e in result.analysis.elements if e.text == marker)
    assert e.selected_decision.role == role
    assert e.selected_decision.action == action
    assert e.selection_source == selection


def test_strong_native_anchor_fallback_through_full_conversion(tmp_path) -> None:
    result = normalize_docx_direct(
        FIXTURES / "sample_02_technical_spec_decimal.docx",
        create_style_pack(name="强锚点验收", format_id="docx"), tmp_path / "native.docx",
        scoring_config=ScoringConfig(medium_score=400, high_score=500),
    )
    e = next(e for e in result.analysis.elements if e.text == "1 范围")
    assert e.selected_decision.role == "heading-1"
    assert e.selected_decision.action == "mapped"
    assert e.selection_source == "legacy"


def test_preserved_only_docx_keeps_original_document_bytes(tmp_path) -> None:
    doc = Document()
    doc.add_paragraph("自动列表内容保持完整原样", style="List Number")
    source, output = tmp_path / "source.docx", tmp_path / "preserved.docx"
    doc.save(source)
    result = normalize_docx_direct(
        source, create_style_pack(name="原始XML验收", format_id="docx"), output,
    )
    with ZipFile(source) as old, ZipFile(output) as new:
        assert old.read("word/document.xml") == new.read("word/document.xml")
    report = json.loads(result.normalization_report_path.read_text(encoding="utf-8"))
    assert report["xml_patch"]["mapped_count"] == 0
    assert "word/document.xml" not in report["modified_xml_parts"]


def test_acceptance_rejects_silently_skipped_selected_mapping(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DOC_CONVERTER_LIBREOFFICE", str(tmp_path / "no-preview"))
    # Deliberately reproduce a broken mapper, while retaining real API conversion/audit.
    monkeypatch.setattr(mapper, "policy_for_role", lambda *a, **kw: PRESERVE_POLICY)
    name = "sample_03_ambiguous_numbering.docx"
    with pytest.raises(AssertionError):
        verify_sample(FIXTURES / name, tmp_path / "broken-mapper", TRUTH[name])
