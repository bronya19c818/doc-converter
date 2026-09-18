"""Deterministic OOXML cleanup after Pandoc has produced a DOCX."""

from __future__ import annotations

import re
from typing import Any

from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from doc_converter.docx_styles import ROLE_TO_STYLE_ID
from doc_converter.normalizer import (
    _extract_front_matter,
    _extract_leading_metadata,
    _normalize_metadata,
)

_ORDERED_LIST = re.compile(r"^(\s*)(\d+)\.(\s+)")
_HEADING_STYLE = re.compile(r"^Heading\s*[1-6]$", re.IGNORECASE)


def split_metadata(markdown: str) -> tuple[dict[str, Any], str]:
    """Remove Front Matter before Pandoc and return normalized metadata."""

    raw_metadata, lines, first_content_line = _extract_front_matter(markdown)
    metadata = _normalize_metadata(raw_metadata)
    extracted, consumed, _ = _extract_leading_metadata(lines, metadata, first_content_line)
    metadata.update(extracted)
    body_lines = [line for index, line in enumerate(lines) if index not in consumed]
    return metadata, "\n".join(body_lines).strip("\n") + "\n"


def protect_ordered_list_literals(markdown: str) -> str:
    """Escape ordered-list markers so Pandoc emits ordinary paragraphs."""

    lines: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        if line.strip().startswith("```") or line.strip().startswith("~~~"):
            in_fence = not in_fence
        if not in_fence:
            line = _ORDERED_LIST.sub(r"\1\2\\.\3", line)
        lines.append(line)
    return "\n".join(lines) + "\n"


def apply_postprocess(document: DocxDocument, metadata: dict[str, Any]) -> None:
    """Apply semantic style IDs, metadata paragraphs, lists and footers."""

    for paragraph in document.paragraphs:
        _map_paragraph(paragraph, ROLE_TO_STYLE_ID["body-paragraph"])
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _map_paragraph(paragraph, ROLE_TO_STYLE_ID["body-table"])

    _insert_metadata(document, metadata)
    _add_page_footers(document)


def _map_paragraph(paragraph: Paragraph, default_style: str) -> None:
    style_id = paragraph.style.style_id if paragraph.style is not None else ""
    if _HEADING_STYLE.match(style_id) or style_id.lower().startswith("heading"):
        paragraph.style = ROLE_TO_STYLE_ID["heading-1"]
    elif style_id not in ROLE_TO_STYLE_ID.values():
        paragraph.style = default_style
    _remove_numbering(paragraph)
    for run in paragraph.runs:
        if run.bold is True:
            run.style = ROLE_TO_STYLE_ID["point"]
            _remove_direct_bold(run)


def _remove_numbering(paragraph: Paragraph) -> None:
    ppr = paragraph._p.pPr
    if ppr is None:
        return
    num_pr = ppr.find(qn("w:numPr"))
    if num_pr is not None:
        ppr.remove(num_pr)


def _remove_direct_bold(run: Any) -> None:
    rpr = run._r.rPr
    if rpr is None:
        return
    for tag in ("w:b", "w:bCs"):
        element = rpr.find(qn(tag))
        if element is not None:
            rpr.remove(element)


def _insert_metadata(document: DocxDocument, metadata: dict[str, Any]) -> None:
    entries: list[tuple[str, str, str]] = []
    if isinstance(metadata.get("title"), str) and metadata["title"].strip():
        entries.append(("document-title", metadata["title"], ROLE_TO_STYLE_ID["document-title"]))
    if isinstance(metadata.get("subtitle"), str) and metadata["subtitle"].strip():
        entries.append(("document-subtitle", metadata["subtitle"], ROLE_TO_STYLE_ID["document-subtitle"]))
    if isinstance(metadata.get("organization"), str) and metadata["organization"].strip():
        entries.append(("organization", metadata["organization"], ROLE_TO_STYLE_ID["organization-department"]))
    if isinstance(metadata.get("department"), str) and metadata["department"].strip():
        entries.append(("department", metadata["department"], ROLE_TO_STYLE_ID["organization-department"]))
    authors = metadata.get("authors")
    if isinstance(authors, list) and authors:
        entries.append(("authors", "、".join(str(author) for author in authors), ROLE_TO_STYLE_ID["author"]))
    if isinstance(metadata.get("date"), str) and metadata["date"].strip():
        entries.append(("date", metadata["date"], ROLE_TO_STYLE_ID["date"]))
    abstract = _strip_metadata_label(metadata.get("abstract"), "摘要")
    if abstract:
        entries.append(("abstract", f"摘要：{abstract}", ROLE_TO_STYLE_ID["abstract"]))
    keywords = _keyword_text(metadata.get("keywords"))
    if keywords:
        entries.append(("keywords", f"关键词：{keywords}", ROLE_TO_STYLE_ID["keywords"]))
    if not entries:
        return

    body = document._body._element
    first = next((child for child in body if child.tag in {qn("w:p"), qn("w:tbl")}), None)
    insert_index = list(body).index(first) if first is not None else len(body)
    for _, text, style_id in entries:
        element = OxmlElement("w:p")
        body.insert(insert_index, element)
        insert_index += 1
        paragraph = Paragraph(element, document)
        paragraph.style = style_id
        paragraph.add_run(text)


def _strip_metadata_label(value: Any, label: str) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return re.sub(rf"^{re.escape(label)}\s*[:：]\s*", "", text).strip()


def _keyword_text(value: Any) -> str:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "；".join(items)
    if isinstance(value, str):
        return _strip_metadata_label(value, "关键词")
    return ""


def _add_page_footers(document: DocxDocument) -> None:
    settings = document.settings._element
    if settings.find(qn("w:evenAndOddHeaders")) is None:
        settings.append(OxmlElement("w:evenAndOddHeaders"))
    for section in document.sections:
        _set_footer(section.footer, "right")
        even_footer = getattr(section, "even_page_footer", None)
        if even_footer is not None:
            _set_footer(even_footer, "left")


def _set_footer(footer: Any, alignment: str) -> None:
    paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    paragraph.style = ROLE_TO_STYLE_ID["footer"]
    paragraph.alignment = {"left": 0, "right": 2}[alignment]
    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)
    paragraph.add_run("－ ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "1"
    run.append(text)
    field.append(run)
    paragraph._p.append(field)
    paragraph.add_run(" －")
