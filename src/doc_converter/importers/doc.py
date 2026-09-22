"""Legacy binary DOC input adapter."""

from dataclasses import replace
from pathlib import Path

from doc_converter.importers.base import ImportResult
from doc_converter.importers.docx import import_docx
from doc_converter.importers.libreoffice import convert_doc_to_docx


def import_doc(source_path: Path, *, job_directory: Path) -> ImportResult:
    """Convert DOC to DOCX first, then extract its content through Pandoc."""

    intermediate_path = job_directory / "source" / "intermediate.docx"
    convert_doc_to_docx(source_path, output_path=intermediate_path)
    imported = import_docx(intermediate_path, job_directory=job_directory)
    return replace(
        imported,
        source_format="doc",
        original_path=source_path,
        intermediate_files=[intermediate_path, *imported.intermediate_files],
    )
