"""LibreOffice discovery and high-fidelity legacy DOC conversion."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from doc_converter.importers.base import ImporterError

_LIBREOFFICE_MISSING = (
    "当前环境未找到 LibreOffice。DOC 为旧版 Word 二进制格式，需要 LibreOffice 完成兼容转换；"
    "DOCX 文件不受影响。"
)


def resolve_libreoffice() -> Path:
    """Find a LibreOffice executable using configuration, PATH, then Windows defaults."""

    configured = os.environ.get("DOC_CONVERTER_LIBREOFFICE", "").strip().strip('"')
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_file():
            return configured_path
        configured_executable = shutil.which(configured)
        if configured_executable is not None:
            return Path(configured_executable)
        raise ImporterError(
            f"DOC_CONVERTER_LIBREOFFICE 指向的 LibreOffice 文件不存在：{configured}"
        )

    for executable_name in ("soffice.com", "soffice", "soffice.exe"):
        executable = shutil.which(executable_name)
        if executable is not None:
            return Path(executable)

    if os.name == "nt":
        program_directories = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "LibreOffice"
            / "program",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
            / "LibreOffice"
            / "program",
        ]
        for program_directory in program_directories:
            for executable_name in ("soffice.com", "soffice.exe"):
                candidate = program_directory / executable_name
                if candidate.is_file():
                    return candidate

    raise ImporterError(_LIBREOFFICE_MISSING)


def convert_doc_to_docx(source_path: Path, *, output_path: Path) -> Path:
    """Convert a binary DOC into an intermediate DOCX using an isolated LO profile."""

    libreoffice_path = resolve_libreoffice()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(prefix="doc-converter-lo-", dir=output_path.parent) as scratch:
            scratch_path = Path(scratch)
            profile_uri = (scratch_path / "profile").as_uri()
            command = [
                str(libreoffice_path),
                "--headless",
                f"-env:UserInstallation={profile_uri}",
                "--convert-to",
                "docx",
                "--outdir",
                str(scratch_path),
                str(source_path),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                cwd=source_path.parent,
                timeout=180,
            )
            converted_path = scratch_path / f"{source_path.stem}.docx"
            if completed.returncode != 0 or not converted_path.is_file():
                detail = completed.stderr.strip() or completed.stdout.strip()
                suffix = f"：{detail}" if detail else "。"
                raise ImporterError(f"LibreOffice 无法将 DOC 转换为 DOCX{suffix}")
            output_path.write_bytes(converted_path.read_bytes())
    except ImporterError:
        raise
    except subprocess.TimeoutExpired as error:
        raise ImporterError("DOC 转换超时，请检查文件是否损坏或过大。") from error
    except OSError as error:
        raise ImporterError(f"无法启动 LibreOffice 转换 DOC：{error}") from error
    return output_path
