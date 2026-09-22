from __future__ import annotations

from pathlib import Path

from docx.oxml import parse_xml
from docx.oxml.ns import qn

from doc_converter.docx_direct.analyzer import analyze_docx
from doc_converter.docx_direct.classifier import classify_document
from doc_converter.docx_direct.ooxml_patch import read_zip_member
from doc_converter.docx_direct.style_mapper import patch_document_xml

FIXTURE = Path(__file__).parent / "fixtures" / "DOCX转Markdown压力测试_V1_结构兼容性.docx"
TEXT_TAGS = {qn("w:t"), qn("w:delText")}
DIRECT_FORMATTING_TAGS = {
    qn("w:rFonts"),
    qn("w:sz"),
    qn("w:szCs"),
    qn("w:color"),
    qn("w:b"),
    qn("w:bCs"),
    qn("w:i"),
    qn("w:iCs"),
}


def classified_fixture():
    return classify_document(analyze_docx(FIXTURE))


def paragraph_text(paragraph) -> str:
    return "".join(node.text or "" for node in paragraph.iter() if node.tag in TEXT_TAGS)


def paragraph_for_text(payload: bytes, marker: str):
    root = parse_xml(payload)
    return next(paragraph for paragraph in root.iter(qn("w:p")) if marker in paragraph_text(paragraph))


def paragraph_style(paragraph) -> str | None:
    properties = paragraph.find(qn("w:pPr"))
    style = properties.find(qn("w:pStyle")) if properties is not None else None
    return style.get(qn("w:val")) if style is not None else None


def test_mapping_changes_only_mapped_paragraph_styles() -> None:
    before = read_zip_member(FIXTURE, "word/document.xml")
    after, report = patch_document_xml(before, classified_fixture())

    assert paragraph_style(paragraph_for_text(after, "CASE-H-001")) == "DC_Heading1"
    assert paragraph_style(paragraph_for_text(after, "CASE-LIST-B1")) == "ListBullet"
    assert paragraph_style(paragraph_for_text(after, "CASE-LIST-LITERAL-001")) is None
    assert report["mapped_count"] >= 1
    assert report["preserved_count"] >= 1

    before_root = parse_xml(before)
    after_root = parse_xml(after)
    assert [node.tag for node in before_root.iter(qn("w:numPr"))] == [
        node.tag for node in after_root.iter(qn("w:numPr"))
    ]


def test_uniform_direct_formatting_is_removed_but_local_semantics_survive() -> None:
    before = read_zip_member(FIXTURE, "word/document.xml")
    after, _ = patch_document_xml(before, classified_fixture())
    root = parse_xml(after)

    uniform = paragraph_for_text(after, "用途：验证 Pandoc")
    assert all(
        node.tag not in DIRECT_FORMATTING_TAGS
        for run in uniform.iter(qn("w:r"))
        for node in run.iter(qn("w:rPr"))
        for node in node
    )

    mixed = paragraph_for_text(after, "CASE-RUN-ANCHOR")
    assert mixed.find(".//" + qn("w:b")) is not None
    assert mixed.find(".//" + qn("w:i")) is not None
    assert mixed.find(".//" + qn("w:vertAlign")) is not None
    assert mixed.find(".//" + qn("w:color")) is not None

    hyperlink = paragraph_for_text(after, "外部超链接：OpenAI")
    assert hyperlink.find(".//" + qn("w:hyperlink")) is not None
    assert paragraph_for_text(after, "CASE-SPACE-001").find(".//" + qn("w:tab")) is not None
    assert paragraph_for_text(after, "CASE-PAGEBREAK-001").find(".//" + qn("w:br")) is not None
    assert len(list(root.iter(qn("w:drawing")))) == 3
    assert len(list(root.iter(qn("w:ins")))) == 1
    assert len(list(root.iter(qn("w:del")))) == 1
