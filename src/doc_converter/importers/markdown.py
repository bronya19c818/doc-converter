"""Markdown input adapter."""

from pathlib import Path

from doc_converter.importers.base import ImporterError, ImportResult


def import_markdown(source_path: Path) -> ImportResult:
    """Decode an uploaded Markdown file without changing its text."""

    try:
        markdown = source_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise ImporterError("Markdown 必须使用 UTF-8 编码。") from error
    except OSError as error:
        raise ImporterError("无法读取上传的 Markdown 文件。") from error
    return ImportResult(
        source_format="markdown",
        markdown=markdown,
        original_path=source_path,
    )
