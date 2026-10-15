"""DOCX rendering through local Pandoc and a self-contained style pack."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx import Document

from doc_converter.docx_extensions import (
    extract_complex_tables,
    extract_page_breaks,
    restore_complex_tables,
    restore_endnotes,
    restore_page_breaks,
)
from doc_converter.docx_postprocess import (
    apply_postprocess,
    split_metadata,
)
from doc_converter.docx_styles import ROLE_TO_STYLE_ID, compile_styles
from doc_converter.markdown_verification import verify_rendered_roles
from doc_converter.normalizer import _code_line_indices, normalize_markdown
from doc_converter.style_library import StylePack


class RendererError(RuntimeError):
    """Raised when a local rendering dependency cannot create the requested DOCX."""


@dataclass(frozen=True)
class RenderResult:
    """The successful DOCX output and deterministic renderer details."""

    output_path: Path
    reference_docx_path: Path
    pandoc_path: Path
    verification: dict[str, Any]


def render_docx(
    *,
    markdown: str,
    style_pack: StylePack,
    output_path: Path,
    work_dir: Path,
    pandoc_path: Path | None = None,
    role_decisions: list[dict[str, Any]] | None = None,
) -> RenderResult:
    """Render Markdown to an editable, self-contained DOCX without network access."""

    if style_pack.format_id != "docx":
        raise ValueError("DOCX 渲染器只能使用 format_id 为 docx 的样式包。")

    resolved_pandoc = pandoc_path or resolve_pandoc()
    work_dir = work_dir.resolve()
    output_path = output_path.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if role_decisions is None:
        normalized = normalize_markdown(markdown, filename="document.md")
        markdown = normalized.markdown
        role_decisions = normalized.report["decisions"]
    metadata, body = split_metadata(markdown)
    body = extract_page_breaks(body)
    body, complex_tables = extract_complex_tables(body)
    source_path = work_dir / "document.body.md"
    reference_path = work_dir / "reference.docx"
    source_path.write_text(body, encoding="utf-8")
    compile_reference_docx(style_pack, reference_path)
    metadata_path = work_dir / "document.metadata.md"
    metadata_path.write_text(metadata_markdown(metadata) + metadata_reference_definitions(body), encoding="utf-8")
    filter_path = work_dir / "metadata.lua"
    filter_path.write_text(
        'function Pandoc(doc)\n'
        '  local f = assert(io.open(os.getenv("DOC_CONVERTER_METADATA"), "r"))\n'
        '  local content = f:read("*a"); f:close()\n'
        '  local prefix = pandoc.read(content, "markdown+fenced_divs+bracketed_spans")\n'
        '  prefix.blocks:extend(doc.blocks)\n'
        '  doc.blocks = prefix.blocks\n'
        '  return doc\nend\n', encoding="utf-8",
    )

    command = [
        str(resolved_pandoc),
        str(source_path),
        "--from=gfm+footnotes+tex_math_dollars+raw_html+subscript+superscript",
        "--to=docx",
        "--standalone",
        f"--reference-doc={reference_path}",
        f"--lua-filter={filter_path}",
        f"--output={output_path}",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=work_dir.parent,
        env={**os.environ, "DOC_CONVERTER_METADATA": str(metadata_path.resolve())},
    )
    if completed.returncode != 0 or not output_path.exists():
        detail = completed.stderr.strip() or completed.stdout.strip() or "Pandoc 未生成 DOCX。"
        raise RendererError(f"DOCX 渲染失败：{detail}")

    document = Document(str(output_path))
    restore_complex_tables(document, complex_tables, resource_root=work_dir.parent)
    restore_page_breaks(document)
    image_role = style_pack.roles.get("image", {})
    image_settings = image_role.get("image", {})
    max_image_width = image_settings.get("max_width_cm") if isinstance(image_settings, dict) else None
    apply_postprocess(
        document,
        {},
        semantic_roles=role_decisions,
        max_image_width_cm=max_image_width if isinstance(max_image_width, (int, float)) else None,
    )
    document.save(str(output_path))
    restore_endnotes(output_path, markdown)
    return RenderResult(output_path=output_path, reference_docx_path=reference_path, pandoc_path=resolved_pandoc,
                        verification=verify_rendered_roles(output_path, role_decisions, style_pack))


def metadata_reference_definitions(body: str) -> str:
    """Share link/note definitions with the metadata parser, including continuations."""
    import re

    lines = body.splitlines()
    protected = _code_line_indices(body)
    output: list[str] = []
    index = 0
    while index < len(lines):
        if index not in protected and re.match(r"^ {0,3}\[[^]]+\]:", lines[index]):
            output.append(lines[index])
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index].startswith(("    ", "\t"))):
                output.append(lines[index])
                index += 1
            output.append("")
        else:
            index += 1
    return "\n".join(output) + "\n"


def metadata_markdown(metadata: dict[str, Any]) -> str:
    """Render metadata through Pandoc too, retaining links, emphasis and code."""
    entries: list[tuple[str, str, str]] = []
    for key, role in (("title", "document-title"), ("subtitle", "document-subtitle"),
                      ("organization", "organization-department"), ("department", "organization-department"),
                      ("authors", "author"), ("date", "date")):
        value = metadata.get(key)
        if isinstance(value, list):
            value = "、".join(str(item) for item in value)
        if isinstance(value, str) and value.strip():
            entries.append((key, role, value))
    for key, label in (("abstract", "摘要"), ("keywords", "关键词")):
        value = metadata.get(key)
        if isinstance(value, list):
            value = "；".join(str(item) for item in value)
        if isinstance(value, str) and value.strip():
            value = value.removeprefix(label + "：").removeprefix(label + ":")
            content_style = ROLE_TO_STYLE_ID[key + "-content"]
            entries.append((key, key + "-label", f'{label}：[{value}]{{custom-style="{content_style}"}}'))
    output: list[str] = []
    order = list(metadata)
    for _, role, text in sorted(entries, key=lambda entry: order.index(entry[0])):
        # Longer fences keep literal ::: lines inside metadata from ending a div.
        fence = ":" * max(4, max((len(line) for line in text.splitlines() if line and set(line) == {":"}), default=0) + 1)
        output.append(f'{fence} {{custom-style="{ROLE_TO_STYLE_ID[role]}"}}\n{text}\n{fence}\n')
    return "\n".join(output) + ("\n" if output else "")


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

