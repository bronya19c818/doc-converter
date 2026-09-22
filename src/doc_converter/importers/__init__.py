"""Document input adapters and their shared import contract."""

from pathlib import Path

from doc_converter.importers.base import ImporterError, ImportResult
from doc_converter.importers.doc import import_doc
from doc_converter.importers.docx import import_docx
from doc_converter.importers.markdown import import_markdown


def import_document(source_path: Path, *, job_directory: Path) -> ImportResult:
    """Import Markdown, DOCX, or DOC into a Markdown working copy."""

    source_format = source_path.suffix.lower()
    if source_format in {".md", ".markdown"}:
        return import_markdown(source_path)
    if source_format == ".docx":
        return import_docx(source_path, job_directory=job_directory)
    if source_format == ".doc":
        return import_doc(source_path, job_directory=job_directory)
    raise ImporterError("当前支持 .md、.markdown、.docx 和 .doc 文件。")


__all__ = ["ImporterError", "ImportResult", "import_document"]
