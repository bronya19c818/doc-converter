"""Orchestration for the isolated direct DOCX normalization experiment."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from doc_converter.docx_direct.analyzer import analyze_docx
from doc_converter.docx_direct.audit import (
    AUDIT_FILENAMES,
    build_normalization_records,
    sha256_file,
    write_audit_bundle,
)
from doc_converter.docx_direct.classifier import classify_document
from doc_converter.docx_direct.model import DecisionMode, DirectNormalizeResult
from doc_converter.docx_direct.ooxml_patch import read_zip_member, write_zip_copy
from doc_converter.docx_direct.scoring import ScoringConfig
from doc_converter.docx_direct.style_injector import inject_styles_into_docx
from doc_converter.docx_direct.style_mapper import patch_document_parts
from doc_converter.style_library import StylePack


def normalize_docx_direct(
    source_path: Path,
    style_pack: StylePack,
    output_path: Path,
    *,
    audit_dir: Path | None = None,
    decision_mode: DecisionMode = "hybrid",
    scoring_config: ScoringConfig | None = None,
) -> DirectNormalizeResult:
    """Normalize a DOCX in a temporary package and commit it atomically."""

    source = Path(source_path)
    output = Path(output_path)
    audit = Path(audit_dir) if audit_dir is not None else output.parent
    source, output, audit = _validate_paths(source, output, audit)

    source_sha256 = sha256_file(source)
    with tempfile.TemporaryDirectory(prefix=".docx-direct-", dir=str(output.parent)) as temporary:
        temporary_dir = Path(temporary)
        staged_styles = temporary_dir / "with-styles.docx"
        staged_output = temporary_dir / "normalized.docx"
        staged_audit = temporary_dir / "audit"

        analysis = classify_document(
            analyze_docx(source), decision_mode=decision_mode, scoring_config=scoring_config,
        )
        if sha256_file(source) != source_sha256:
            raise ValueError("源文件在分析期间发生变化，已取消规范化。")

        style_report = inject_styles_into_docx(source, style_pack, staged_styles)
        before_document = read_zip_member(staged_styles, "word/document.xml")
        replacements, patch_report = patch_document_parts(
            before_document,
            analysis,
            styles_payload=read_zip_member(staged_styles, "word/styles.xml"),
        )
        write_zip_copy(
            staged_styles,
            staged_output,
            replacements,
        )
        _validate_output_docx(staged_output)
        if sha256_file(source) != source_sha256:
            raise ValueError("源文件在写出期间发生变化，已取消规范化。")

        output_sha256 = sha256_file(staged_output)
        records = build_normalization_records(analysis)
        source_unchanged = sha256_file(source) == source_sha256
        if not source_unchanged:
            raise ValueError("源文件在审计前发生变化，已取消规范化。")
        write_audit_bundle(
            staged_audit,
            analysis=analysis,
            records=records,
            style_pack=style_pack,
            source_sha256=source_sha256,
            output_sha256=output_sha256,
            source_unchanged=source_unchanged,
            style_report=style_report,
            patch_report=patch_report,
        )
        _commit_outputs(staged_output, output, staged_audit, audit, temporary_dir)

    return DirectNormalizeResult(
        output_path=output,
        analysis_path=audit / "docx-analysis.json",
        normalization_report_path=audit / "docx-normalization-report.json",
        style_pack_snapshot_path=audit / "style-pack.snapshot.json",
        analysis=analysis,
        records=records,
    )


def _validate_paths(source: Path, output: Path, audit: Path) -> tuple[Path, Path, Path]:
    if not source.is_file():
        raise ValueError(f"源 DOCX 不存在或不是文件：{source}")
    source_resolved = source.resolve()
    output_resolved = output.resolve()
    if source_resolved == output_resolved:
        raise ValueError("源文件和输出文件不能相同。")
    if output.exists() and output.is_dir():
        raise ValueError(f"输出路径不能是目录：{output}")
    if output.parent.exists() and not output.parent.is_dir():
        raise ValueError(f"输出目录不可用：{output.parent}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if audit.exists() and not audit.is_dir():
        raise ValueError(f"审计目录不可用：{audit}")
    if not audit.parent.exists() or not audit.parent.is_dir():
        raise ValueError(f"审计目录的父目录不可用：{audit.parent}")
    if any((audit / filename).resolve() == output_resolved for filename in AUDIT_FILENAMES):
        raise ValueError("输出文件不能覆盖审计产物。")
    return source, output, audit


def _validate_output_docx(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError("规范化输出的 DOCX ZIP 校验失败。")
            required = {"[Content_Types].xml", "word/document.xml", "word/styles.xml"}
            missing = required - set(archive.namelist())
            if missing:
                raise ValueError(f"规范化输出缺少 DOCX 部件：{', '.join(sorted(missing))}")
    except (BadZipFile, OSError) as error:
        raise ValueError("规范化输出不是可读取的 DOCX。") from error


def _commit_outputs(
    staged_output: Path,
    output: Path,
    staged_audit: Path,
    audit: Path,
    temporary_dir: Path,
) -> None:
    backup_output = temporary_dir / "previous-output.docx"
    audit_backups: dict[Path, Path] = {}
    replaced_audit: list[Path] = []
    created_audit_dir = False
    output_committed = False
    try:
        if output.exists():
            os.replace(output, backup_output)
        os.replace(staged_output, output)
        output_committed = True

        if not audit.exists():
            audit.mkdir(parents=True, exist_ok=True)
            created_audit_dir = True
        for filename in AUDIT_FILENAMES:
            target = audit / filename
            if target.exists():
                if target.is_dir():
                    raise ValueError(f"审计产物路径不能是目录：{target}")
                backup = temporary_dir / f"previous-{filename}"
                os.replace(target, backup)
                audit_backups[target] = backup
            os.replace(staged_audit / filename, target)
            replaced_audit.append(target)
    except Exception:
        for target in reversed(replaced_audit):
            if target.exists():
                target.unlink()
        for target, backup in audit_backups.items():
            if backup.exists():
                os.replace(backup, target)
        if created_audit_dir and audit.exists() and not any(audit.iterdir()):
            audit.rmdir()
        if output_committed and output.exists():
            output.unlink()
        if backup_output.exists():
            os.replace(backup_output, output)
        raise
    if backup_output.exists():
        backup_output.unlink()
