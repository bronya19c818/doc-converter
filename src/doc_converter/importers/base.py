"""Shared contracts for input-format importers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class ImporterError(RuntimeError):
    """Raised when a source document cannot be imported into Markdown."""


@dataclass(frozen=True)
class ImportResult:
    """Canonical Markdown and source-side artifacts produced by an importer."""

    source_format: str
    markdown: str
    original_path: Path
    assets_dir: Path | None = None
    intermediate_files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
