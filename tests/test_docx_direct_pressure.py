from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from docx.oxml import parse_xml
from docx.oxml.ns import qn
from lxml import etree

from doc_converter.docx_direct.normalizer import normalize_docx_direct
from doc_converter.docx_direct.ooxml_patch import read_zip_member
from doc_converter.style_library import create_style_pack

FIXTURE = Path(__file__).parent / "fixtures" / "DOCX转Markdown压力测试_V1_结构兼容性.docx"
TEXT_TAGS = {qn("w:t"), qn("w:delText")}
STRUCTURAL_TAGS = {
    qn("w:tblPr"),
    qn("w:tblGrid"),
    qn("w:gridSpan"),
    qn("w:vMerge"),
}


def paragraph_text(paragraph) -> str:
    return "".join(node.text or "" for node in paragraph.iter() if node.tag in TEXT_TAGS)


def paragraph_style_for_text(path: Path, marker: str) -> str | None:
    root = parse_xml(read_zip_member(path, "word/document.xml"))
    paragraph = next(paragraph for paragraph in root.iter(qn("w:p")) if marker in paragraph_text(paragraph))
    properties = paragraph.find(qn("w:pPr"))
    style = properties.find(qn("w:pStyle")) if properties is not None else None
    return style.get(qn("w:val")) if style is not None else None


def anchors_in_order(path: Path, anchors: list[str]) -> bool:
    root = parse_xml(read_zip_member(path, "word/document.xml"))
    text = "\n".join(paragraph_text(paragraph) for paragraph in root.iter(qn("w:p")))
    positions = [text.index(anchor) for anchor in anchors]
    return positions == sorted(positions)


def package_payload(path: Path, member: str) -> bytes:
    return read_zip_member(path, member)


def relationship_targets(path: Path) -> list[tuple[str, str, str]]:
    root = parse_xml(read_zip_member(path, "word/_rels/document.xml.rels"))
    return sorted(
        (
            relation.get("Id", ""),
            relation.get("Type", ""),
            relation.get("Target", ""),
        )
        for relation in root
    )


def image_count(path: Path) -> int:
    root = parse_xml(read_zip_member(path, "word/document.xml"))
    return len(list(root.iter(qn("w:drawing"))))


def table_merge_signature(path: Path) -> list[bytes]:
    root = parse_xml(read_zip_member(path, "word/document.xml"))
    return [
        etree.tostring(node, method="c14n")
        for node in root.iter()
        if node.tag in STRUCTURAL_TAGS
    ]


def test_pressure_document_maps_targets_and_preserves_package_structures(tmp_path: Path) -> None:
    output = tmp_path / "out.docx"
    audit_dir = tmp_path / "audit"
    result = normalize_docx_direct(
        FIXTURE,
        create_style_pack(name="pressure", format_id="docx"),
        output,
        audit_dir=audit_dir,
    )

    assert result.output_path == output
    assert paragraph_style_for_text(output, "CASE-H-001 标题层级与正文结构") == "DC_Heading1"
    assert paragraph_style_for_text(output, "一、一级中文编号但使用普通正文样式 〔CASE-MANUAL-001〕") == "DC_Heading1"
    assert paragraph_style_for_text(output, "（一）二级中文编号但使用普通正文样式 〔CASE-MANUAL-002〕") == "DC_Heading2"
    assert paragraph_style_for_text(output, "CASE-TBL-001 表格结构") == "DC_Heading1"
    assert anchors_in_order(
        output,
        ["CASE-RUN-ANCHOR", "CASE-SPACE-001", "CASE-LINK-001", "CASE-EN-001", "CASE-REV-001"],
    )

    for member in ("word/numbering.xml", "word/footnotes.xml", "word/endnotes.xml"):
        assert package_payload(output, member) == package_payload(FIXTURE, member)
    assert relationship_targets(output) == relationship_targets(FIXTURE)
    assert image_count(output) == image_count(FIXTURE) == 3
    assert table_merge_signature(output) == table_merge_signature(FIXTURE)

    report = result.normalization_report_path.read_text(encoding="utf-8")
    assert '"mapped"' in report
    with ZipFile(output) as archive:
        assert archive.testzip() is None
