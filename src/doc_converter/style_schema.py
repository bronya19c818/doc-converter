"""Structured, portable DOCX style-role definitions.

The JSON representation intentionally keeps the nested ``font`` and
``paragraph`` objects explicit.  This makes the style editor extensible while
still allowing older style packs, which stored flat ``font_name`` fields, to
be read and upgraded deterministically.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ROLE_KEYS = (
    "document-title",
    "document-subtitle",
    "organization-department",
    "author",
    "date",
    "abstract-label",
    "abstract-content",
    "keywords-label",
    "keywords-content",
    "heading-1",
    "heading-2",
    "heading-3",
    "heading-4",
    "heading-5",
    "heading-6",
    "body-paragraph",
    "body-table",
    "table-row-header",
    "table-column-header",
    "point",
    "table-caption",
    "table-credit",
    "figure-caption",
    "figure-credit",
    "image",
    "reference-heading",
    "reference-entry",
    "footer",
    "page",
)

IndentUnit = Literal["character", "pt", "cm"]
LineSpacingRule = Literal["maximum", "minimum", "exact", "multiple"]


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
    first_line_indent_unit: IndentUnit = "character"
    left_indent_pt: float = 0
    left_indent_unit: IndentUnit = "character"
    right_indent_pt: float = 0
    right_indent_unit: IndentUnit = "character"
    space_before_pt: float = 0
    space_after_pt: float = 0
    line_spacing_pt: float | None = None
    line_spacing_rule: LineSpacingRule = "exact"
    line_spacing_multiple: float | None = None
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
    page_width_cm: float = 21.0
    page_height_cm: float = 29.7


class ImageSpec(BaseModel):
    """Layout controls for embedded document images."""

    model_config = ConfigDict(extra="ignore")

    alignment: Literal["left", "center", "right"] = "center"
    max_width_cm: float | None = Field(default=None, gt=0)
    space_before_pt: float = 0
    space_after_pt: float = 0


class StyleRole(BaseModel):
    """A role is a paragraph, character, page, or image definition."""

    model_config = ConfigDict(extra="ignore")

    role_type: Literal["paragraph", "character", "page", "image"] = "paragraph"
    font: FontSpec | None = None
    paragraph: ParagraphSpec | None = None
    page: PageSpec | None = None
    image: ImageSpec | None = None


def _role(
    *,
    role_type: Literal["paragraph", "character", "page", "image"] = "paragraph",
    font: dict[str, Any] | None = None,
    paragraph: dict[str, Any] | None = None,
    page: dict[str, Any] | None = None,
    image: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = StyleRole(
        role_type=role_type,
        font=FontSpec(**(font or {})) if role_type not in {"page", "image"} else None,
        paragraph=ParagraphSpec(**(paragraph or {})) if role_type == "paragraph" else None,
        page=PageSpec(**(page or {})) if role_type == "page" else None,
        image=ImageSpec(**(image or {})) if role_type == "image" else None,
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
        "abstract-label": _role(
            font={"chinese_font": "黑体", "western_font": "Times New Roman", "size_pt": 9, "bold": True},
            paragraph={
                "alignment": "justify",
                "first_line_indent_pt": 0,
                "left_indent_pt": 18,
                "left_indent_unit": "character",
                "right_indent_pt": 18,
                "right_indent_unit": "character",
                "space_before_pt": 12,
                "line_spacing_pt": 12,
                "line_spacing_rule": "minimum",
            },
        ),
        "abstract-content": _role(
            role_type="character",
            font={"chinese_font": "楷体", "western_font": "Times New Roman", "size_pt": 9},
        ),
        "keywords-label": _role(
            font={"chinese_font": "黑体", "western_font": "Times New Roman", "size_pt": 9, "bold": True},
            paragraph={
                "alignment": "justify",
                "left_indent_pt": 18,
                "left_indent_unit": "character",
                "right_indent_pt": 18,
                "right_indent_unit": "character",
                "space_after_pt": 5,
                "line_spacing_pt": 12,
                "line_spacing_rule": "minimum",
            },
        ),
        "keywords-content": _role(
            role_type="character",
            font={"chinese_font": "楷体", "western_font": "Times New Roman", "size_pt": 9},
        ),
        "heading-1": _role(
            font={"chinese_font": "黑体", "western_font": "Times New Roman", "size_pt": 14, "bold": True},
            paragraph={"space_before_pt": 5, "line_spacing_pt": 18, "line_spacing_rule": "minimum"},
        ),
        "heading-2": _role(
            font={"chinese_font": "黑体", "western_font": "Times New Roman", "size_pt": 12, "bold": True},
            paragraph={"space_before_pt": 5, "line_spacing_pt": 12, "line_spacing_rule": "minimum"},
        ),
        "heading-3": _role(
            font={"chinese_font": "黑体", "western_font": "Times New Roman", "size_pt": 10.5, "bold": True},
            paragraph={"space_before_pt": 5, "line_spacing_pt": 12, "line_spacing_rule": "minimum"},
        ),
        "heading-4": _role(
            font={"chinese_font": "黑体", "western_font": "Times New Roman", "size_pt": 9, "bold": True},
            paragraph={"space_before_pt": 5, "line_spacing_pt": 12, "line_spacing_rule": "minimum"},
        ),
        "heading-5": _role(
            font={"chinese_font": "黑体", "western_font": "Times New Roman", "size_pt": 7.5, "bold": True},
            paragraph={"space_before_pt": 5, "line_spacing_pt": 12, "line_spacing_rule": "minimum"},
        ),
        "heading-6": _role(
            font={"chinese_font": "黑体", "western_font": "Times New Roman", "size_pt": 6.5, "bold": True},
            paragraph={"space_before_pt": 5, "line_spacing_pt": 12, "line_spacing_rule": "minimum"},
        ),
        "body-paragraph": _role(
            font={"chinese_font": "仿宋", "western_font": "Times New Roman", "size_pt": 16},
            paragraph={"first_line_indent_pt": 32, "line_spacing_pt": 29},
        ),
        "body-table": _role(
            font={"chinese_font": "仿宋", "western_font": "Times New Roman", "size_pt": 14},
            paragraph=no_indent,
        ),
        "table-row-header": _role(
            font={"chinese_font": "仿宋", "western_font": "Times New Roman", "size_pt": 14, "bold": True},
            paragraph=no_indent,
        ),
        "table-column-header": _role(
            font={"chinese_font": "仿宋", "western_font": "Times New Roman", "size_pt": 14, "bold": True},
            paragraph={**no_indent, "alignment": "center"},
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
        "table-credit": _role(
            font={"chinese_font": "黑体", "western_font": "Arial", "size_pt": 14},
            paragraph={"alignment": "right"},
        ),
        "figure-credit": _role(
            font={"chinese_font": "黑体", "western_font": "Arial", "size_pt": 14},
            paragraph={"alignment": "right"},
        ),
        "image": _role(
            role_type="image",
            image={
                "alignment": "center",
                "max_width_cm": None,
                "space_before_pt": 0,
                "space_after_pt": 0,
            },
        ),
        "reference-heading": _role(
            font={"chinese_font": "黑体", "western_font": "Times New Roman", "size_pt": 14, "bold": True},
            paragraph={"space_before_pt": 5, "line_spacing_pt": 18, "line_spacing_rule": "minimum"},
        ),
        "reference-entry": _role(
            font={"chinese_font": "宋体", "western_font": "Times New Roman", "size_pt": 7.5},
            paragraph={"alignment": "justify", "line_spacing_pt": 12, "line_spacing_rule": "minimum"},
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
                "page_width_cm": 21.0,
                "page_height_cm": 29.7,
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
    raw_nested = value.get("paragraph")
    nested: dict[str, Any] = raw_nested if isinstance(raw_nested, dict) else {}
    paragraph.update(nested)
    source_keys = set(value) | set(nested)
    aliases = {
        "first_line_indent_pt": "first_line_indent_pt",
        "first_line_indent_unit": "first_line_indent_unit",
        "left_indent_pt": "left_indent_pt",
        "left_indent_unit": "left_indent_unit",
        "right_indent_pt": "right_indent_pt",
        "right_indent_unit": "right_indent_unit",
        "space_before_pt": "space_before_pt",
        "space_after_pt": "space_after_pt",
        "line_spacing_pt": "line_spacing_pt",
        "line_spacing_rule": "line_spacing_rule",
        "line_spacing_multiple": "line_spacing_multiple",
        "alignment": "alignment",
        "keep_with_next": "keep_with_next",
        "widow_control": "widow_control",
        "page_break_before": "page_break_before",
    }
    for source_key, target_key in aliases.items():
        if source_key in value:
            paragraph[target_key] = value[source_key]
    for source_key, target_key in aliases.items():
        if source_key in nested:
            paragraph[target_key] = nested[source_key]

    # Legacy ``*_indent_pt`` fields were always point values. New packs carry
    # an explicit unit; only infer points when the unit is absent.
    for value_key, unit_key in (
        ("first_line_indent_pt", "first_line_indent_unit"),
        ("left_indent_pt", "left_indent_unit"),
        ("right_indent_pt", "right_indent_unit"),
    ):
        if value_key in source_keys and unit_key not in source_keys:
            paragraph[unit_key] = "pt"

    normalized = ParagraphSpec(**paragraph).model_dump()
    if normalized["line_spacing_rule"] == "multiple" and normalized["line_spacing_multiple"] is None:
        normalized["line_spacing_multiple"] = 1.5
    return normalized


def migrate_roles(raw_roles: Any) -> dict[str, dict[str, Any]]:
    """Merge legacy flat roles into a complete schema-v3 role dictionary.

    Metadata labels are paragraph roles because alignment and indentation
    apply to their entire inline label/content row. Content roles remain
    character styles. Older packs stored the paragraph layout on the content
    role (or on legacy ``abstract`` / ``keywords`` roles), so move that layout
    while preserving both roles' font settings.
    """

    source = raw_roles if isinstance(raw_roles, dict) else {}
    defaults = default_roles()
    aliases = {"body": "body-paragraph"}
    for old_key, new_key in aliases.items():
        if old_key in source and new_key not in source:
            source = {**source, new_key: source[old_key]}

    for legacy_key, label_key, content_key in (
        ("abstract", "abstract-label", "abstract-content"),
        ("keywords", "keywords-label", "keywords-content"),
    ):
        legacy = source.get(legacy_key)
        label = source.get(label_key)
        content = source.get(content_key)
        legacy = legacy if isinstance(legacy, dict) else {}
        label = label if isinstance(label, dict) else {}
        content = content if isinstance(content, dict) else {}

        label_has_layout = label.get("role_type") == "paragraph" or _has_paragraph_data(label)
        content_has_layout = content.get("role_type") == "paragraph" or _has_paragraph_data(content)
        layout_source = label if label_has_layout else content if content_has_layout else legacy
        content_font_source = content if content else legacy

        source = {
            **source,
            label_key: {
                "role_type": "paragraph",
                "font": _font_from_legacy(label, defaults[label_key]),
                "paragraph": _paragraph_from_legacy(layout_source, defaults[label_key]),
            },
            content_key: {
                "role_type": "character",
                "font": _font_from_legacy(content_font_source, defaults[content_key]),
            },
        }
        source.pop(legacy_key, None)

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
        if role_key == "image":
            image_data = value.get("image")
            image = dict(fallback.get("image", {}))
            if isinstance(image_data, dict):
                image.update(image_data)
            migrated[role_key] = _role(role_type="image", image=image)
            continue
        role_type: Literal["paragraph", "character"] = (
            "character" if fallback.get("role_type") == "character" or role_key == "point" else "paragraph"
        )
        migrated[role_key] = _role(
            role_type=role_type,
            font=_font_from_legacy(value, fallback),
            paragraph=_paragraph_from_legacy(value, fallback) if role_type == "paragraph" else None,
        )
    return migrated


def _has_paragraph_data(value: dict[str, Any]) -> bool:
    """Return whether a legacy role contains paragraph-layout fields."""

    if isinstance(value.get("paragraph"), dict):
        return True
    return any(
        key in value
        for key in (
            "alignment",
            "first_line_indent_pt",
            "left_indent_pt",
            "right_indent_pt",
            "space_before_pt",
            "space_after_pt",
            "line_spacing_pt",
            "line_spacing_rule",
            "line_spacing_multiple",
            "keep_with_next",
            "widow_control",
            "page_break_before",
        )
    )
