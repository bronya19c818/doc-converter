"""DOCX rendering through a local Pandoc process and compiled style packs."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.shared import Inches, Pt

from doc_converter.style_library import StylePack

_ROLE_TO_WORD_STYLE = {
    "document-title": "Title",
    "document-subtitle": "Subtitle",
    "heading-1": "Heading 1",
    "heading-2": "Heading 2",
    "heading-3": "Heading 3",
    "heading-4": "Heading 4",
    "heading-5": "Heading 5",
    "heading-6": "Heading 6",
    "body": "Normal",
    "blockquote": "Quote",
    "figure-caption": "Caption",
    "table-caption": "Caption",
    "code-block": "Source Code",
}


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
    """Render normalized Markdown to an editable DOCX without network access."""

    if style_pack.format_id != "docx":
        raise ValueError("DOCX 渲染器只能使用 format_id 为 docx 的样式包。")

    resolved_pandoc = pandoc_path or resolve_pandoc()
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_path = work_dir / "document.normalized.md"
    reference_path = work_dir / "reference.docx"
    source_path.write_text(markdown, encoding="utf-8")
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
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    if completed.returncode != 0 or not output_path.exists():
        detail = completed.stderr.strip() or completed.stdout.strip() or "Pandoc 未生成 DOCX。"
        raise RendererError(f"DOCX 渲染失败：{detail}")

    return RenderResult(
        output_path=output_path,
        reference_docx_path=reference_path,
        pandoc_path=resolved_pandoc,
    )


def compile_reference_docx(style_pack: StylePack, output_path: Path) -> None:
    """Compile a semantic JSON style pack into a Pandoc reference DOCX."""

    document = Document()
    section = document.sections[0]
    page = style_pack.roles.get("page", {})
    _set_margin(section, "top_margin", page.get("margin_top_in"))
    _set_margin(section, "bottom_margin", page.get("margin_bottom_in"))
    _set_margin(section, "left_margin", page.get("margin_left_in"))
    _set_margin(section, "right_margin", page.get("margin_right_in"))

    for role, word_style_name in _ROLE_TO_WORD_STYLE.items():
        style = _get_or_add_paragraph_style(document, word_style_name)
        _apply_style_properties(style, style_pack.roles.get(role, {}))

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


def _get_or_add_paragraph_style(document: DocxDocument, style_name: str) -> Any:
    try:
        return document.styles[style_name]
    except KeyError:
        return document.styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)


def _apply_style_properties(style: Any, properties: dict[str, object]) -> None:
    font = style.font
    font_name = properties.get("font_name")
    if isinstance(font_name, str):
        font.name = font_name
        font._element.rPr.rFonts.set("w:eastAsia", font_name)
    font_size_pt = properties.get("font_size_pt")
    if isinstance(font_size_pt, (int, float)):
        font.size = Pt(font_size_pt)
    for key in ("bold", "italic"):
        value = properties.get(key)
        if isinstance(value, bool):
            setattr(font, key, value)

    paragraph_format = style.paragraph_format
    first_line_indent_pt = properties.get("first_line_indent_pt")
    if isinstance(first_line_indent_pt, (int, float)):
        paragraph_format.first_line_indent = Pt(first_line_indent_pt)
    space_before_pt = properties.get("space_before_pt")
    if isinstance(space_before_pt, (int, float)):
        paragraph_format.space_before = Pt(space_before_pt)
    space_after_pt = properties.get("space_after_pt")
    if isinstance(space_after_pt, (int, float)):
        paragraph_format.space_after = Pt(space_after_pt)


def _set_margin(section: Any, attribute: str, inches: object) -> None:
    if isinstance(inches, (int, float)):
        setattr(section, attribute, Inches(inches))
