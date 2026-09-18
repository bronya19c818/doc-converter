"""Safe output-name helpers for local Windows document artifacts."""

from __future__ import annotations

import re
from pathlib import Path

_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_docx_filename(title: str | None, source_name: str) -> str:
    """Return a clean ``.docx`` filename derived from title or source stem."""

    candidate = (title or "").strip() or Path(source_name).stem or "document"
    candidate = _INVALID_WINDOWS_CHARS.sub("_", candidate).strip(" .") or "document"
    return f"{candidate[:120]}.docx"
