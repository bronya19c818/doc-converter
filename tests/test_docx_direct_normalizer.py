from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from doc_converter.docx_direct.normalizer import normalize_docx_direct
from doc_converter.style_library import create_style_pack

FIXTURE = Path(__file__).parent / "fixtures" / "DOCX转Markdown压力测试_V1_结构兼容性.docx"


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_normalizer_never_modifies_source_and_writes_audit_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "normalized.docx"
    audit_dir = tmp_path / "audit"
    before = file_sha256(FIXTURE)

    result = normalize_docx_direct(
        FIXTURE,
        create_style_pack(name="test", format_id="docx"),
        output,
        audit_dir=audit_dir,
    )

    assert output.is_file()
    assert result.analysis_path == audit_dir / "docx-analysis.json"
    assert result.normalization_report_path == audit_dir / "docx-normalization-report.json"
    assert result.style_pack_snapshot_path == audit_dir / "style-pack.snapshot.json"
    assert file_sha256(FIXTURE) == before

    report = json.loads(result.normalization_report_path.read_text(encoding="utf-8"))
    assert report["source_sha256"] == before
    assert report["source_unchanged"] is True
    assert report["output_sha256"] == file_sha256(output)
    assert all(item["target_style"] for item in report["elements"] if item["action"] == "mapped")


def test_normalizer_rejects_same_path_and_invalid_docx_without_artifacts(tmp_path: Path) -> None:
    before = file_sha256(FIXTURE)
    with pytest.raises(ValueError, match="源文件和输出文件不能相同"):
        normalize_docx_direct(
            FIXTURE,
            create_style_pack(name="test", format_id="docx"),
            FIXTURE,
            audit_dir=tmp_path / "same-path-audit",
        )
    assert file_sha256(FIXTURE) == before

    invalid = tmp_path / "invalid.docx"
    invalid.write_bytes(b"not a docx")
    output = tmp_path / "invalid-output.docx"
    audit_dir = tmp_path / "invalid-audit"
    with pytest.raises(ValueError):
        normalize_docx_direct(
            invalid,
            create_style_pack(name="test", format_id="docx"),
            output,
            audit_dir=audit_dir,
        )
    assert not output.exists()
    assert not audit_dir.exists()


def test_normalizer_rejects_unwritable_output_parent_before_creating_artifacts(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("a file, not a directory", encoding="utf-8")
    audit_dir = tmp_path / "blocked-audit"

    with pytest.raises(ValueError, match="输出目录"):
        normalize_docx_direct(
            FIXTURE,
            create_style_pack(name="test", format_id="docx"),
            blocked_parent / "output.docx",
            audit_dir=audit_dir,
        )
    assert not audit_dir.exists()
