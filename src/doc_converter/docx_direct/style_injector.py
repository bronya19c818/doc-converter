"""Incremental insertion of the direct-normalizer style pack into DOCX."""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from lxml import etree  # type: ignore[import-untyped]

from doc_converter.docx_direct.ooxml_patch import read_zip_member, write_zip_copy
from doc_converter.docx_styles import ROLE_TO_STYLE_ID, compile_styles
from doc_converter.style_library import StylePack


def inject_styles_into_docx(
    source_path: Path,
    style_pack: StylePack,
    output_path: Path,
) -> dict[str, Any]:
    """Add missing ``DC_*`` styles without replacing existing package content."""

    source_styles = parse_xml(read_zip_member(source_path, "word/styles.xml"))
    compiled_styles = _compiled_style_elements(style_pack)
    existing_ids = _style_ids(source_styles)
    target_ids = set(ROLE_TO_STYLE_ID.values())
    missing_ids = [style_id for style_id in target_ids if style_id not in existing_ids]

    inserted_elements = [
        deepcopy(compiled_styles[style_id])
        for style_id in sorted(missing_ids)
        if style_id in compiled_styles
    ]
    _insert_styles(source_styles, inserted_elements)

    replacements: dict[str, bytes] = {}
    if inserted_elements:
        replacements["word/styles.xml"] = etree.tostring(
            source_styles,
            encoding="UTF-8",
            xml_declaration=True,
        )
    write_zip_copy(source_path, output_path, replacements)

    inserted_ids = [
        style_id
        for style_id in sorted(missing_ids)
        if style_id in compiled_styles
    ]
    return {
        "source_path": str(source_path),
        "output_path": str(output_path),
        "inserted_count": len(inserted_ids),
        "inserted_style_ids": inserted_ids,
        "replaced_count": 0,
        "existing_style_count": len(existing_ids),
    }


def _compiled_style_elements(style_pack: StylePack) -> dict[str, Any]:
    document = Document()
    compile_styles(document, style_pack)
    buffer = BytesIO()
    document.save(buffer)
    root = parse_xml(_read_buffer_member(buffer.getvalue(), "word/styles.xml"))
    return {
        style_id: style
        for style in root.findall(qn("w:style"))
        if (style_id := style.get(qn("w:styleId"))) in set(ROLE_TO_STYLE_ID.values())
    }


def _read_buffer_member(payload: bytes, member: str) -> bytes:
    from zipfile import ZipFile

    with ZipFile(BytesIO(payload)) as archive:
        return archive.read(member)


def _style_ids(root: Any) -> set[str]:
    return {
        style_id
        for style in root.findall(qn("w:style"))
        if (style_id := style.get(qn("w:styleId"))) is not None
    }


def _insert_styles(root: Any, styles: list[Any]) -> None:
    if not styles:
        return
    existing = root.findall(qn("w:style"))
    if existing:
        insertion_index = max(root.index(style) for style in existing) + 1
    else:
        insertion_index = len(root)
    for offset, style in enumerate(styles):
        root.insert(insertion_index + offset, style)
