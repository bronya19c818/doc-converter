"""Compilation of structured roles into self-contained OOXML styles."""

from __future__ import annotations

import re
from typing import Any

from docx.document import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

from doc_converter.style_library import StylePack
from doc_converter.style_schema import migrate_roles

ROLE_TO_STYLE_ID = {
    "document-title": "DC_DocumentTitle",
    "document-subtitle": "DC_DocumentSubtitle",
    "organization-department": "DC_OrganizationDepartment",
    "author": "DC_Author",
    "date": "DC_Date",
    "abstract-label": "DC_AbstractLabel",
    "abstract-content": "DC_AbstractContent",
    "keywords-label": "DC_KeywordsLabel",
    "keywords-content": "DC_KeywordsContent",
    "heading-1": "DC_Heading1",
    "heading-2": "DC_Heading2",
    "heading-3": "DC_Heading3",
    "heading-4": "DC_Heading4",
    "heading-5": "DC_Heading5",
    "heading-6": "DC_Heading6",
    "body-paragraph": "DC_BodyParagraph",
    "body-table": "DC_TableBody",
    "table-row-header": "DC_TableRowHeader",
    "table-column-header": "DC_TableColumnHeader",
    "point": "DC_Point",
    "table-caption": "DC_TableCaption",
    "figure-caption": "DC_FigureCaption",
    "image": "DC_Image",
    "reference-heading": "DC_ReferenceHeading",
    "reference-entry": "DC_ReferenceEntry",
    "footer": "DC_Footer",
}


def compile_styles(document: DocxDocument, style_pack: StylePack) -> None:
    """Add all DC styles and page defaults to ``document``."""

    roles = migrate_roles(style_pack.roles)
    page = roles.get("page", {}).get("page", {})
    section = document.sections[0]
    for attribute, key in (
        ("top_margin", "margin_top_cm"),
        ("bottom_margin", "margin_bottom_cm"),
        ("left_margin", "margin_left_cm"),
        ("right_margin", "margin_right_cm"),
        ("page_width", "page_width_cm"),
        ("page_height", "page_height_cm"),
    ):
        value = page.get(key)
        if isinstance(value, (int, float)):
            if attribute in {"page_width", "page_height"}:
                setattr(section, attribute, Mm(round(float(value) * 10)))
            else:
                setattr(section, attribute, Cm(value))

    for role, style_id in ROLE_TO_STYLE_ID.items():
        role_data = roles.get(role, {})
        role_type = role_data.get("role_type", "paragraph")
        style_type = WD_STYLE_TYPE.CHARACTER if role_type == "character" else WD_STYLE_TYPE.PARAGRAPH
        style = _get_or_add_style(document, style_id, style_type)
        _apply_role(style, role_data, style_type, role)

    _set_doc_defaults(document, roles.get("body-paragraph", {}))


def _get_or_add_style(document: DocxDocument, style_id: str, style_type: WD_STYLE_TYPE) -> Any:
    try:
        style = document.styles[style_id]
    except KeyError:
        style = document.styles.add_style(style_id, style_type)
    style.name = style_id
    return style


def _apply_role(
    style: Any,
    role_data: dict[str, Any],
    style_type: WD_STYLE_TYPE,
    role: str | None = None,
) -> None:
    font_data = role_data.get("font", {})
    font = style.font
    chinese = font_data.get("chinese_font")
    western = font_data.get("western_font")
    if isinstance(chinese, str) or isinstance(western, str):
        _set_font_slots(style._element.get_or_add_rPr(), chinese or western, western or chinese)
        if isinstance(western, str):
            font.name = western
    size = font_data.get("size_pt")
    if isinstance(size, (int, float)):
        font.size = Pt(size)
    font_size_pt = float(size) if isinstance(size, (int, float)) else 16.0
    for key in ("bold", "italic"):
        value = font_data.get(key)
        if isinstance(value, bool):
            setattr(font, key, value)
    color = font_data.get("color")
    color_value = re_color(color) if isinstance(color, str) else None
    if color_value:
        font.color.rgb = RGBColor.from_string(color_value)

    if style_type != WD_STYLE_TYPE.CHARACTER:
        paragraph_data = role_data.get("paragraph", {})
        if role == "image":
            image_data = role_data.get("image", {})
            paragraph_data = {
                "alignment": image_data.get("alignment", "center"),
                "space_before_pt": image_data.get("space_before_pt", 0),
                "space_after_pt": image_data.get("space_after_pt", 0),
            }
        _apply_paragraph(style, paragraph_data, font_size_pt)
        if role and role.startswith("heading-"):
            _set_outline_level(style, role)


def _set_outline_level(style: Any, role: str) -> None:
    """Make custom heading styles participate in Word's outline/TOC model."""

    match = re.match(r"heading-([1-6])$", role)
    if match is None:
        return
    ppr = style._element.get_or_add_pPr()
    outline = ppr.find(qn("w:outlineLvl"))
    if outline is None:
        outline = OxmlElement("w:outlineLvl")
        ppr.append(outline)
    outline.set(qn("w:val"), str(int(match.group(1)) - 1))


def _apply_paragraph(style: Any, data: dict[str, Any], font_size_pt: float) -> None:
    paragraph = style.paragraph_format
    alignments = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }
    if data.get("alignment") in alignments:
        paragraph.alignment = alignments[data["alignment"]]
    for attribute, key in (
        ("first_line_indent", "first_line_indent_pt"),
        ("left_indent", "left_indent_pt"),
        ("right_indent", "right_indent_pt"),
        ("space_before", "space_before_pt"),
        ("space_after", "space_after_pt"),
    ):
        value = data.get(key)
        if isinstance(value, (int, float)):
            setattr(paragraph, attribute, Pt(value))
    _apply_indent_units(style, data, font_size_pt)
    _apply_line_spacing(paragraph, data)
    for attribute in ("keep_with_next", "widow_control", "page_break_before"):
        value = data.get(attribute)
        if isinstance(value, bool):
            setattr(paragraph, attribute, value)


def _apply_indent_units(style: Any, data: dict[str, Any], font_size_pt: float) -> None:
    ppr = style._element.get_or_add_pPr()
    indent = ppr.find(qn("w:ind"))
    if indent is None:
        indent = OxmlElement("w:ind")
        ppr.append(indent)
    for value_key, unit_key, chars_attr, points_attr in (
        ("first_line_indent_pt", "first_line_indent_unit", "w:firstLineChars", "w:firstLine"),
        ("left_indent_pt", "left_indent_unit", "w:leftChars", "w:left"),
        ("right_indent_pt", "right_indent_unit", "w:rightChars", "w:right"),
    ):
        value = data.get(value_key)
        if not isinstance(value, (int, float)):
            continue
        if data.get(unit_key, "pt") == "character":
            characters = round(float(value) / max(font_size_pt, 0.01) * 100)
            indent.set(qn(chars_attr), str(characters))
        else:
            indent.attrib.pop(qn(chars_attr), None)


def _apply_line_spacing(paragraph: Any, data: dict[str, Any]) -> None:
    rule = data.get("line_spacing_rule", "exact")
    if rule == "multiple":
        multiple = data.get("line_spacing_multiple")
        if not isinstance(multiple, (int, float)):
            multiple = 1.0
        paragraph.line_spacing = float(multiple)
        paragraph.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        return

    line_spacing = data.get("line_spacing_pt")
    if not isinstance(line_spacing, (int, float)):
        return
    paragraph.line_spacing = Pt(line_spacing)
    rule_map = {
        "minimum": WD_LINE_SPACING.AT_LEAST,
        "exact": WD_LINE_SPACING.EXACTLY,
    }
    if rule in rule_map:
        paragraph.line_spacing_rule = rule_map[rule]
        return
    if rule == "maximum":
        # OOXML has no maximum rule. ``auto`` keeps the requested twip value
        # while allowing Word/WPS to resolve the line box from its font.
        spacing = paragraph._element.get_or_add_pPr().find(qn("w:spacing"))
        if spacing is not None:
            spacing.set(qn("w:lineRule"), "auto")


def _set_doc_defaults(document: DocxDocument, role_data: dict[str, Any]) -> None:
    font_data = role_data.get("font", {})
    chinese = font_data.get("chinese_font")
    western = font_data.get("western_font")
    if not isinstance(chinese, str) and not isinstance(western, str):
        return
    styles_element = document.styles.element
    doc_defaults = styles_element.find(qn("w:docDefaults"))
    if doc_defaults is None:
        doc_defaults = OxmlElement("w:docDefaults")
        styles_element.insert(0, doc_defaults)
    rpr_default = doc_defaults.find(qn("w:rPrDefault"))
    if rpr_default is None:
        rpr_default = OxmlElement("w:rPrDefault")
        doc_defaults.append(rpr_default)
    rpr = rpr_default.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        rpr_default.append(rpr)
    _set_font_slots(rpr, chinese or western, western or chinese)


def _set_font_slots(rpr: Any, chinese: str, western: str) -> None:
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for slot in ("eastAsia", "ascii", "hAnsi", "cs"):
        rfonts.set(qn(f"w:{slot}"), chinese if slot == "eastAsia" else western)


def re_color(value: str) -> str | None:
    candidate = value.strip().lstrip("#")
    return candidate.upper() if len(candidate) == 6 and all(char in "0123456789ABCDEFabcdef" for char in candidate) else None
