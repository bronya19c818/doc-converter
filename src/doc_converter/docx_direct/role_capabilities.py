"""Declared Direct capabilities; no implicit first-row or first-column guessing."""

from typing import Any

from doc_converter.style_schema import ROLE_KEYS


def role_capabilities() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for role in ROLE_KEYS:
        inline = role in {"abstract-content", "keywords-content"}
        preserve = role in {"point", "table-row-header"}
        outside = role in {"footer", "page"}
        result[role] = {
            "style_pack": True,
            "status": "out-of-scope" if outside else "preserve-only" if preserve else "supported",
            "automatic_recognition": not (preserve or outside),
            "paragraph_execution": not (inline or preserve or outside),
            "character_execution": not (preserve or outside or role == "image"),
            "evidence": "standalone inline pictures only; paragraph layout; source dimensions preserved" if role == "image" else
                        "explicit tblHeader only" if role == "table-column-header" else
                        "explicit Chinese label only" if role.startswith(("abstract-", "keywords-")) else
                        "style only; no automatic assignment" if preserve else
                        "source preserved" if outside else "selected_decision",
        }
    return result
