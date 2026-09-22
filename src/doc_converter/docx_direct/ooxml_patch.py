"""Small ZIP/XML payload helpers for direct DOCX normalization."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from docx.oxml import parse_xml
from lxml import etree


def parse_xml_payload(payload: bytes):
    """Parse an OOXML payload with the same namespace-aware parser as python-docx."""

    return parse_xml(payload)


def serialize_xml_payload(root) -> bytes:
    """Serialize an OOXML tree without dropping its namespace declarations."""

    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def read_zip_member(source_path: Path, member: str) -> bytes:
    """Read one raw member payload from a DOCX ZIP package."""

    with ZipFile(source_path) as archive:
        return archive.read(member)


def write_zip_copy(
    source_path: Path,
    output_path: Path,
    replacements: Mapping[str, bytes],
) -> None:
    """Copy a ZIP package while replacing only the requested member payloads."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source_path) as source, ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        source_names = {info.filename for info in source.infolist()}
        unknown_members = set(replacements) - source_names
        if unknown_members:
            missing = ", ".join(sorted(unknown_members))
            raise KeyError(f"ZIP replacement member(s) not found: {missing}")
        for info in source.infolist():
            payload = replacements.get(info.filename, source.read(info.filename))
            target.writestr(info, payload)
