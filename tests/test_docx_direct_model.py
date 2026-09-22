from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from doc_converter.docx_direct.model import (
    DirectNormalizeResult,
    DocumentAnalysis,
    ElementAnalysis,
    NormalizationRecord,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_pressure_fixture_is_the_user_provided_docx() -> None:
    source = Path(r"C:\Users\Lenovo\Downloads\DOCX转Markdown压力测试_V1_结构兼容性.docx")
    fixture = Path(__file__).parent / "fixtures" / source.name
    assert source.is_file(), f"缺少用户指定压力测试文件：{source}"
    assert fixture.is_file()
    assert _sha256(source) == _sha256(fixture)


def _element(**overrides: Any) -> ElementAnalysis:
    values: dict[str, Any] = {
        "element_id": "p-0001",
        "element_type": "paragraph",
        "text": "一、项目建设目标",
        "document_order": 0,
        "xml_path": (0, 1),
        "region": "body",
        "original_style_id": "Normal",
        "original_style_name": "Normal",
        "role": "heading-1",
        "confidence": 0.96,
        "action": "mapped",
        "reasons": ["中文一级编号", "独立段落"],
    }
    values.update(overrides)
    return ElementAnalysis(**values)


def test_direct_analysis_models_round_trip_through_json_data() -> None:
    element = _element()
    analysis = DocumentAnalysis(
        source_sha256="a" * 64,
        elements=[element],
        package_entries=["word/document.xml", "word/styles.xml"],
        main_document_stats={"tables": 0, "sections": 1, "inline_shapes": 0},
    )
    record = NormalizationRecord(
        element_id=element.element_id,
        text=element.text,
        original_style_id=element.original_style_id,
        original_style_name=element.original_style_name,
        detected_role=element.role,
        confidence=element.confidence,
        action=element.action,
        target_style="DC_Heading1",
        reasons=element.reasons,
    )
    result = DirectNormalizeResult(
        output_path=Path("out.docx"),
        analysis_path=Path("docx-analysis.json"),
        normalization_report_path=Path("docx-normalization-report.json"),
        style_pack_snapshot_path=Path("style-pack.snapshot.json"),
        analysis=analysis,
        records=[record],
    )

    restored = DocumentAnalysis.model_validate(analysis.model_dump())
    restored_result = DirectNormalizeResult.model_validate(result.model_dump())

    assert restored.elements[0] == element
    assert restored_result.records[0] == record
    assert restored_result.output_path == Path("out.docx")


def test_element_confidence_and_action_are_constrained() -> None:
    with pytest.raises(ValidationError):
        _element(confidence=1.01)
    with pytest.raises(ValidationError):
        _element(action="changed")
