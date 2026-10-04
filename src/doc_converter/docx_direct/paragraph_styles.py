"""Retain inherited structural paragraph properties when replacing pStyle."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from doc_converter.docx_direct.model import PropertyDecision, TransformationAudit
from doc_converter.docx_direct.ooxml_patch import parse_xml_payload
from doc_converter.docx_direct.transformation_policy import TransformationPolicy


def _merge(base: Any | None, override: Any) -> Any:
    if base is None:
        return deepcopy(override)
    result = deepcopy(base)
    result.attrib.update(override.attrib)
    for child in override:
        existing = result.find(child.tag)
        if existing is not None:
            result.remove(existing)
        result.append(deepcopy(child))
    return result


class ParagraphStylePreserver:
    """Copy source inheritance locally; never edit numbering or source styles."""

    def __init__(self, payload: bytes) -> None:
        root = parse_xml_payload(payload)
        self.styles = {s.get(qn("w:styleId")): s for s in root.findall(qn("w:style"))}
        self.default_style = next(
            (
                key
                for key, s in self.styles.items()
                if s.get(qn("w:type")) == "paragraph" and s.get(qn("w:default")) == "1"
            ),
            None,
        )
        self.defaults = root.find("w:docDefaults/w:pPrDefault/w:pPr", root.nsmap)

    def preserve(
        self, paragraph: Any, policy: TransformationPolicy, audit: TransformationAudit
    ) -> bool:
        properties = paragraph.find(qn("w:pPr"))
        style = properties.find(qn("w:pStyle")) if properties is not None else None
        current = style.get(qn("w:val")) if style is not None else self.default_style
        chain: list[Any] = []
        visited: set[str] = set()
        while current:
            source = self.styles.get(current)
            if source is None or current in visited or len(chain) >= 64:
                audit.transform_safety = "preserve"
                audit.skipped_properties.append(
                    PropertyDecision(
                        property="pStyle",
                        level="paragraph",
                        mode="preserve",
                        reason="源段落样式继承缺失或循环，整段保留以避免丢失结构属性",
                    )
                )
                return False
            visited.add(current)
            source_properties = source.find(qn("w:pPr"))
            if source_properties is not None:
                chain.append(source_properties)
            parent = source.find(qn("w:basedOn"))
            current = parent.get(qn("w:val")) if parent is not None else None
        layers = ([self.defaults] if self.defaults is not None else []) + list(reversed(chain))
        inherited: dict[str, Any] = {}
        for layer in layers:
            for tag in ("numPr", "ind", "pageBreakBefore", "keepNext", "outlineLvl"):
                value = layer.find(qn("w:" + tag))
                if value is not None:
                    inherited[tag] = _merge(inherited.get(tag), value)
        has_numbering = "numPr" in inherited or (
            properties is not None and properties.find(qn("w:numPr")) is not None
        )
        for tag, value in inherited.items():
            if policy.paragraph_properties.get(tag) != "preserve" and not (
                tag == "ind" and has_numbering
            ):
                continue
            direct = properties.find(qn("w:" + tag)) if properties is not None else None
            merged = _merge(value, direct) if direct is not None else deepcopy(value)
            if direct is not None and _same_properties(merged, direct):
                continue
            if properties is None:
                properties = OxmlElement("w:pPr")
                paragraph.insert(0, properties)
            if direct is not None:
                properties.replace(direct, merged)
            else:
                # Respect CT_PPr ordering using python-docx's property inserters.
                inserter = getattr(properties, "_insert_" + tag, None)
                if inserter is not None:
                    inserter(merged)
                else:
                    properties.insert_element_before(
                        merged, "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange"
                    )
            audit.preserved_properties.append(
                PropertyDecision(
                    property=tag,
                    level="paragraph",
                    mode="preserve",
                    reason="将源段落样式中的继承结构属性保留为直接属性，换样式后仍有效",
                )
            )
            audit.transform_safety = "guarded"
        return True


def _same_properties(left: Any, right: Any) -> bool:
    return left.attrib == right.attrib and [(child.tag, dict(child.attrib)) for child in left] == [
        (child.tag, dict(child.attrib)) for child in right
    ]
