"""Narrow structural evidence for text-free, inline picture paragraphs."""

from typing import Any

from docx.oxml.ns import qn

PICTURE_URI = "http://schemas.openxmlformats.org/drawingml/2006/picture"


def is_inline_picture_run(run: Any) -> bool:
    if run.tag != qn("w:r") or any(child.tag not in {qn("w:rPr"), qn("w:drawing")} for child in run):
        return False
    drawings = run.findall(qn("w:drawing"))
    if not drawings:
        return False
    for drawing in drawings:
        if len(drawing) != 1 or drawing[0].tag != qn("wp:inline"):
            return False
        inline = drawing[0]
        if any(child.tag not in {qn("wp:extent"), qn("wp:effectExtent"), qn("wp:docPr"),
                                 qn("wp:cNvGraphicFramePr"), qn("a:graphic")} for child in inline):
            return False
        graphics = inline.findall(qn("a:graphic"))
        if len(graphics) != 1 or len(graphics[0]) != 1:
            return False
        data = graphics[0].findall(qn("a:graphicData"))
        if (len(data) != 1 or data[0].get("uri") != PICTURE_URI
                or len(data[0]) != 1 or data[0][0].tag != qn("pic:pic")):
            return False
        if any(node.tag in {qn("w:t"), qn("a:t"), qn("w:txbxContent")} for node in drawing.iter()):
            return False
    return True


def is_standalone_picture(paragraph: Any) -> bool:
    content = [child for child in paragraph if child.tag not in {
        qn("w:pPr"), qn("w:bookmarkStart"), qn("w:bookmarkEnd"),
    }]
    return bool(content) and all(is_inline_picture_run(child) for child in content)
