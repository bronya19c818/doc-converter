"""Structured, portable DOCX style-role definitions.

The JSON representation intentionally keeps the nested ``font`` and
``paragraph`` objects explicit.  This makes the style editor extensible while
still allowing older style packs, which stored flat ``font_name`` fields, to
be read and upgraded deterministically.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ROLE_KEYS = (
    "document-title",
    "document-subtitle",
    "organization-department",
    "author",
    "date",
    "heading-1",
    "body-paragraph",
    "body-table",
    "point",
    "table-caption",
    "figure-caption",
    "footer",
    "page",
)


class FontSpec(BaseModel):
    """Font slots that are written to all relevant Word font attributes."""

    model_config = ConfigDict(extra="ignore")

    chinese_font: str = "仿宋"
    western_font: str = "Times New Roman"
    size_pt: float = 16
    bold: bool = False
    italic: bool = False
    color: str | None = None


class ParagraphSpec(BaseModel):
    """Deterministic paragraph formatting shared by paragraph roles."""

    model_config = ConfigDict(extra="ignore")

    alignment: Literal["left", "center", "right", "justify"] = "left"
    first_line_indent_pt: float = 0
    left_indent_pt: float = 0
    right_indent_pt: float = 0
    space_before_pt: float = 0
    space_after_pt: float = 0
    line_spacing_pt: float | None = None
    keep_with_next: bool = False
    widow_control: bool = True
    page_break_before: bool = False


class PageSpec(BaseModel):
    """Page settings expressed in centimetres for the editor."""

    model_config = ConfigDict(extra="ignore")

    margin_top_cm: float = 3.5
    margin_bottom_cm: float = 3.5
    margin_left_cm: float = 2.8
    margin_right_cm: float = 2.8


class StyleRole(BaseModel):
    """A role is either a paragraph, character, or page definition."""

    model_config = ConfigDict(extra="ignore")

    role_type: Literal["paragraph", "character", "page"] = "paragraph"
    font: FontSpec | None = None
    paragraph: ParagraphSpec | None = None
    page: PageSpec | None = None


def _role(
    *,
    role_type: Literal["paragraph", "character", "page"] = "paragraph",
    font: dict[str, Any] | None = None,
    paragraph: dict[str, Any] | None = None,
    page: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = StyleRole(
        role_type=role_type,
        font=FontSpec(**(font or {})) if role_type != "page" else None,
        paragraph=ParagraphSpec(**(paragraph or {})) if role_type == "paragraph" else None,
        page=PageSpec(**(page or {})) if role_type == "page" else None,
    )
    return value.model_dump(exclude_none=True)


def default_roles() -> dict[str, dict[str, Any]]:
    """Return a fresh complete set of Chinese formal-document defaults."""

    centered = {"alignment": "center"}
    no_indent = {"first_line_indent_pt": 0}
    return {
        "document-title": _role(
            font={"chinese_font": "宋体", "western_font": "Times New Roman", "size_pt": 22, "bold": True},
            paragraph=centered,
        ),
        "document-subtitle": _role(
            font={"chinese_font": "楷体", "western_font": "Times New Roman", "size_pt": 16, "bold": True},
            paragraph=centered,
        ),
        "organization-department": _role(
            font={"chinese_font": "楷体", "western_font": "Times New Roman", "size_pt": 16, "bold": True},
            paragraph=centered,
        ),
        "author": _role(
            font={"chinese_font": "楷体", "western_font": "Times New Roman", "size_pt": 16, "bold": True},
            paragraph=centered,
        ),
        "date": _role(
            font={"chinese_font": "楷体", "western_font": "Times New Roman", "size_pt": 16, "bold": True},
            paragraph=centered,
        ),
        "heading-1": _role(
            font={"chinese_font": "黑体", "western_font": "Arial", "size_pt": 16, "bold": True},
            paragraph={"first_line_indent_pt": 32},
        ),
        "body-paragraph": _role(
            font={"chinese_font": "仿宋", "western_font": "Times New Roman", "size_pt": 16},
            paragraph={"first_line_indent_pt": 32, "line_spacing_pt": 29},
        ),
        "body-table": _role(
            font={"chinese_font": "仿宋", "western_font": "Times New Roman", "size_pt": 14},
            paragraph=no_indent,
        ),
        "point": _role(
            role_type="character",
            font={"chinese_font": "楷体", "western_font": "Times New Roman", "size_pt": 16, "bold": True},
        ),
        "table-caption": _role(
            font={"chinese_font": "黑体", "western_font": "Arial", "size_pt": 14, "bold": True},
            paragraph={"alignment": "left"},
        ),
        "figure-caption": _role(
            font={"chinese_font": "黑体", "western_font": "Arial", "size_pt": 14, "bold": True},
            paragraph=centered,
        ),
        "footer": _role(
            font={"chinese_font": "宋体", "western_font": "Times New Roman", "size_pt": 14},
            paragraph=centered,
        ),
        "page": _role(
            role_type="page",
            page={
                "margin_top_cm": 3.5,
                "margin_bottom_cm": 3.5,
                "margin_left_cm": 2.8,
                "margin_right_cm": 2.8,
            },
        ),
    }


def _font_from_legacy(value: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    font = dict(fallback.get("font", {}))
    if isinstance(value.get("font"), dict):
        font.update(value["font"])
    if isinstance(value.get("font_name"), str):
        font["chinese_font"] = value["font_name"]
    if isinstance(value.get("western_font"), str):
        font["western_font"] = value["western_font"]
    if isinstance(value.get("font_size_pt"), (int, float)):
        font["size_pt"] = value["font_size_pt"]
    for key in ("bold", "italic", "color"):
        if key in value:
            font[key] = value[key]
    return FontSpec(**font).model_dump()


def _paragraph_from_legacy(value: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    paragraph = dict(fallback.get("paragraph", {}))
    if isinstance(value.get("paragraph"), dict):
        paragraph.update(value["paragraph"])
    aliases = {
        "first_line_indent_pt": "first_line_indent_pt",
        "left_indent_pt": "left_indent_pt",
        "right_indent_pt": "right_indent_pt",
        "space_before_pt": "space_before_pt",
        "space_after_pt": "space_after_pt",
        "line_spacing_pt": "line_spacing_pt",
        "alignment": "alignment",
        "keep_with_next": "keep_with_next",
        "widow_control": "widow_control",
        "page_break_before": "page_break_before",
    }
    for source_key, target_key in aliases.items():
        if source_key in value:
            paragraph[target_key] = value[source_key]
    return ParagraphSpec(**paragraph).model_dump()


def migrate_roles(raw_roles: Any) -> dict[str, dict[str, Any]]:
    """Merge legacy flat roles into a complete schema-v2 role dictionary."""

    source = raw_roles if isinstance(raw_roles, dict) else {}
    defaults = default_roles()
    aliases = {"body": "body-paragraph"}
    for old_key, new_key in aliases.items():
        if old_key in source and new_key not in source:
            source = {**source, new_key: source[old_key]}

    migrated: dict[str, dict[str, Any]] = {}
    for role_key in ROLE_KEYS:
        fallback = defaults[role_key]
        value = source.get(role_key, {})
        if not isinstance(value, dict):
            value = {}
        if role_key == "page":
            page = dict(fallback.get("page", {}))
            page.update(value.get("page", value))
            migrated[role_key] = _role(role_type="page", page=page)
            continue
        role_type: Literal["paragraph", "character"] = "character" if role_key == "point" else "paragraph"
        migrated[role_key] = _role(
            role_type=role_type,
            font=_font_from_legacy(value, fallback),
            paragraph=_paragraph_from_legacy(value, fallback) if role_type == "paragraph" else None,
        )
    return migrated
