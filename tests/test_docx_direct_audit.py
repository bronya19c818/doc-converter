from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from doc_converter.docx_direct.normalizer import normalize_docx_direct
from doc_converter.style_library import create_style_pack


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _make_inherited_title_docx(path: Path) -> None:
    document = Document()
    style = document.styles.add_style("TitleInherited", WD_STYLE_TYPE.PARAGRAPH)
    style.font.size = Pt(22)
    style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph("继承格式标题", style="TitleInherited")
    document.save(path)


def test_audit_preserves_direct_and_effective_evidence(tmp_path: Path) -> None:
    source = tmp_path / "inherited.docx"
    output = tmp_path / "normalized.docx"
    audit_dir = tmp_path / "audit"
    _make_inherited_title_docx(source)
    before = _sha256(source)

    result = normalize_docx_direct(
        source,
        create_style_pack(name="test", format_id="docx"),
        output,
        audit_dir=audit_dir,
    )

    payload = json.loads(result.analysis_path.read_text(encoding="utf-8"))
    item = next(item for item in payload["elements"] if item["text"] == "继承格式标题")

    assert payload["evidence_fields"] == [
        "paragraph_properties",
        "run_properties",
        "effective_format",
        "signals",
    ]
    assert item["paragraph_properties"] == {}
    assert item["effective_format"]["font_size_pt"] == 22
    assert item["signals"]["style_chain"] == ["TitleInherited"]
    assert item["role"] == "document-title"
    assert item["action"] == "mapped"
    assert item["reasons"]

    report = json.loads(result.normalization_report_path.read_text(encoding="utf-8"))
    records = report["elements"]
    assert report["counts"]["mapped"] == sum(record["action"] == "mapped" for record in records)
    assert all(record["target_style"] for record in records if record["action"] == "mapped")
    assert all(record["target_style"] is None for record in records if record["action"] != "mapped")
    assert _sha256(source) == before
    assert output.is_file()
    assert {path.name for path in audit_dir.iterdir()} == {
        "docx-analysis.json",
        "docx-normalization-report.json",
        "style-pack.snapshot.json",
    }
