from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from doc_converter.docx_direct.analyzer import analyze_docx

FIXTURE = Path(__file__).parent / "fixtures" / "DOCX转Markdown压力测试_V1_结构兼容性.docx"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_analyzer_reports_pressure_document_without_writing_source() -> None:
    before = _sha256(FIXTURE)
    result = analyze_docx(FIXTURE)

    assert result.source_sha256 == before
    assert len(result.elements) > 86
    assert result.main_document_stats["tables"] == 4
    assert result.main_document_stats["sections"] == 3
    assert result.main_document_stats["inline_shapes"] == 3
    assert any(item.text == "CASE-H-001 标题层级与正文结构" for item in result.elements)
    assert any(item.table_context for item in result.elements)
    assert len({item.xml_path for item in result.elements}) == len(result.elements)
    assert _sha256(FIXTURE) == before


def test_analyzer_rejects_invalid_docx_zip(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.docx"
    invalid.write_bytes(b"not a zip")

    with pytest.raises(ValueError, match="有效.*DOCX|ZIP"):
        analyze_docx(invalid)


def test_analyzer_rejects_package_without_main_document(tmp_path: Path) -> None:
    missing_document = tmp_path / "missing-document.docx"
    with ZipFile(missing_document, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types />")

    with pytest.raises(ValueError, match="word/document.xml"):
        analyze_docx(missing_document)
