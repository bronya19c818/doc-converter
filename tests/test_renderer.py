from docx import Document

from doc_converter.renderer import render_docx, resolve_pandoc
from doc_converter.style_library import create_style_pack


def test_renderer_creates_editable_docx_from_normalized_markdown(tmp_path) -> None:
    markdown = """---
schema: normalized-md/v1
title: 项目建设方案
organization: XX公司
department: XX部门
---

# 一、建设背景

正文包含 **重点内容** 和 [项目链接](https://example.com)。

| 项目 | 数量 |
| --- | ---: |
| A | 10 |
"""
    output_path = tmp_path / "项目建设方案.docx"

    render_docx(
        markdown=markdown,
        style_pack=create_style_pack(name="测试样式", format_id="docx"),
        output_path=output_path,
        work_dir=tmp_path / "work",
    )

    document = Document(output_path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert output_path.exists()
    assert "项目建设方案" in text
    assert "一、建设背景" in text
    assert "重点内容" in text
    assert document.tables[0].cell(1, 1).text == "10"


def test_renderer_prefers_bundled_pandoc_when_available(tmp_path) -> None:
    bundled_root = tmp_path / "pandoc"
    bundled_root.mkdir()
    bundled_executable = bundled_root / "pandoc.exe"
    bundled_executable.write_bytes(b"not-executed-in-this-test")

    assert resolve_pandoc(bundled_root=bundled_root) == bundled_executable
