"""DOCX rendering through local Pandoc and a self-contained style pack."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from docx import Document

from doc_converter.docx_postprocess import (
    apply_postprocess,
    protect_ordered_list_literals,
    split_metadata,
)
from doc_converter.docx_styles import compile_styles
from doc_converter.style_library import StylePack


class RendererError(RuntimeError):
    """Raised when a local rendering dependency cannot create the requested DOCX."""


@dataclass(frozen=True)
class RenderResult:
    """The successful DOCX output and deterministic renderer details."""

    output_path: Path
    reference_docx_path: Path
    pandoc_path: Path


def render_docx(
    *,
    markdown: str,
    style_pack: StylePack,
    output_path: Path,
    work_dir: Path,
    pandoc_path: Path | None = None,
) -> RenderResult:
    """Render Markdown to an editable, self-contained DOCX without network access."""

    if style_pack.format_id != "docx":
        raise ValueError("DOCX 渲染器只能使用 format_id 为 docx 的样式包。")

    resolved_pandoc = pandoc_path or resolve_pandoc()
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata, body = split_metadata(markdown)
    source_path = work_dir / "document.body.md"
    reference_path = work_dir / "reference.docx"
    source_path.write_text(protect_ordered_list_literals(body), encoding="utf-8")
    compile_reference_docx(style_pack, reference_path)

    command = [
        str(resolved_pandoc),
        str(source_path),
        "--from=gfm+footnotes+tex_math_dollars+raw_html",
        "--to=docx",
        "--standalone",
        f"--reference-doc={reference_path}",
        f"--output={output_path}",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=work_dir.parent,
    )
    if completed.returncode != 0 or not output_path.exists():
        detail = completed.stderr.strip() or completed.stdout.strip() or "Pandoc 未生成 DOCX。"
        raise RendererError(f"DOCX 渲染失败：{detail}")

    document = Document(str(output_path))
    image_role = style_pack.roles.get("image", {})
    image_settings = image_role.get("image", {})
    max_image_width = image_settings.get("max_width_cm") if isinstance(image_settings, dict) else None
    apply_postprocess(
        document,
        metadata,
        max_image_width_cm=max_image_width if isinstance(max_image_width, (int, float)) else None,
    )
    document.save(str(output_path))
    return RenderResult(output_path=output_path, reference_docx_path=reference_path, pandoc_path=resolved_pandoc)


def compile_reference_docx(style_pack: StylePack, output_path: Path) -> None:
    """Compile structured roles into a Pandoc reference DOCX."""

    document = Document()
    compile_styles(document, style_pack)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output_path))


def resolve_pandoc(*, bundled_root: Path | None = None) -> Path:
    """Resolve a bundled Pandoc first, then an explicitly configured system copy."""

    executable_name = "pandoc.exe" if os.name == "nt" else "pandoc"
    bundled_directory = bundled_root or Path(__file__).resolve().parent / "vendor" / "pandoc"
    bundled_executable = bundled_directory / executable_name
    if bundled_executable.exists():
        return bundled_executable

    configured_path = os.environ.get("DOC_CONVERTER_PANDOC")
    if configured_path:
        configured_executable = Path(configured_path)
        if configured_executable.exists():
            return configured_executable
        raise RendererError("DOC_CONVERTER_PANDOC 指向的 Pandoc 文件不存在。")

    executable = shutil.which("pandoc")
    if executable is None:
        raise RendererError("未找到内置或系统 Pandoc，无法生成 DOCX。")
    return Path(executable)
