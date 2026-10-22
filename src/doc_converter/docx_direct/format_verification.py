"""Verify the written package's effective formatting, never just target IDs."""

from pathlib import Path
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree  # type: ignore[import-untyped]

from doc_converter.docx_direct.analyzer import _iter_paragraphs, analyze_docx
from doc_converter.docx_direct.effective_format import EffectiveFormatResolver
from doc_converter.docx_direct.formatting import _text_runs, protected_field_runs
from doc_converter.docx_direct.model import DocumentAnalysis
from doc_converter.docx_direct.ooxml_patch import parse_xml_payload, read_zip_member
from doc_converter.docx_direct.protected_format import (
    FORMAT_KEYS,
    external_text_baseline,
    protected_run_indices,
)
from doc_converter.docx_direct.style_injector import _compiled_style_elements
from doc_converter.docx_direct.transformation_policy import policy_for_role
from doc_converter.docx_styles import ROLE_TO_STYLE_ID
from doc_converter.style_library import StylePack


def verify_effective_format(analysis: DocumentAnalysis, output: Path, pack: StylePack, source: Path) -> None:
    written = analyze_docx(output)
    if [(e.xml_path, e.text) for e in analysis.elements] != [(e.xml_path, e.text) for e in written.elements]:
        raise ValueError("转换后段落位置或可见文字发生变化。")
    compiled = _compiled_style_elements(pack)
    styles = OxmlElement("w:styles")
    for style in compiled.values():
        styles.append(style)
    resolver = EffectiveFormatResolver(styles, structural_guard=True)
    expected: dict[str, dict[str, Any]] = {}
    for role, sid in ROLE_TO_STYLE_ID.items():
        p = OxmlElement("w:p")
        run = OxmlElement("w:r")
        if role.endswith("-content"):
            rpr = OxmlElement("w:rPr")
            rstyle = OxmlElement("w:rStyle")
            rstyle.set(qn("w:val"), sid)
            rpr.append(rstyle)
            run.append(rpr)
        t = OxmlElement("w:t")
        t.text = "验"
        run.append(t)
        p.append(run)
        paragraph_sid = ROLE_TO_STYLE_ID[role.replace("-content", "-label")] if role.endswith("-content") else sid
        expected[role] = resolver.resolve_paragraph(p, paragraph_style_id=paragraph_sid)
    root = parse_xml_payload(read_zip_member(output, "word/document.xml"))
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("输出缺少 w:body。")
    paragraphs = {path: p for p, path, _ in _iter_paragraphs(body)}
    field_runs = protected_field_runs(body)
    source_root = parse_xml_payload(read_zip_member(source, "word/document.xml"))
    source_body = source_root.find(qn("w:body"))
    if source_body is None:
        raise ValueError("源文件缺少 w:body。")
    source_paragraphs = {path: p for p, path, _ in _iter_paragraphs(source_body)}
    source_fields = protected_field_runs(source_body)
    source_resolver = EffectiveFormatResolver(parse_xml_payload(read_zip_member(source, "word/styles.xml")), structural_guard=True)
    output_styles = parse_xml_payload(read_zip_member(output, "word/styles.xml"))
    style_map = {s.get(qn("w:styleId")): s for s in output_styles.findall(qn("w:style"))}
    output_resolver = EffectiveFormatResolver(output_styles, structural_guard=True)

    def semantic_override(run: Any, prop: str, target_id: str) -> bool:
        rpr = run.find(qn("w:rPr"))
        if rpr is not None and rpr.find(qn("w:" + prop)) is not None:
            return True
        rstyle = rpr.find(qn("w:rStyle")) if rpr is not None else None
        sid = rstyle.get(qn("w:val")) if rstyle is not None else None
        visited: set[str] = set()
        while sid and sid != target_id and sid not in visited and len(visited) < 64:
            visited.add(sid)
            style = style_map.get(sid)
            if style is None:
                return False
            props = style.find(qn("w:rPr"))
            if props is not None and props.find(qn("w:" + prop)) is not None:
                return True
            parent = style.find(qn("w:basedOn"))
            sid = parent.get(qn("w:val")) if parent is not None else None
        return False
    for before, after in zip(analysis.elements, written.elements, strict=True):
        audit = before.transformation
        decision = before.selected_decision
        if audit is None or decision is None:
            raise ValueError("输出缺少转换审计。")
        audit.effective_style_after = after.original_style_id
        original_p = source_paragraphs[before.xml_path]
        p = paragraphs[after.xml_path]
        effective_after = output_resolver.resolve_paragraph(p, paragraph_style_id=after.original_style_id)
        after.effective_format = {k: v for k, v in effective_after.items() if k not in {"style_chain", "based_on_heading"}}
        audit.effective_format_after = after.effective_format
        old_indices = sorted(protected_run_indices(original_p, source_fields))
        new_indices = sorted(protected_run_indices(p, field_runs))
        if len(old_indices) != len(new_indices):
            raise ValueError("受保护 Run 数量变化。")
        old_values = source_resolver.resolve_paragraph(original_p, paragraph_style_id=None)["run_statistics"]["runs"] if old_indices else []
        new_values = output_resolver.resolve_paragraph(p, paragraph_style_id=None)["run_statistics"]["runs"] if new_indices else []
        image_layout = (
            decision.role == "image" and audit.style_application_status in {"applied", "guarded"}
            and before.signals.get("standalone_image") and after.signals.get("standalone_image")
        )
        if image_layout:
            old_content = [etree.tostring(n, method="c14n", exclusive=True) for n in original_p if n.tag != qn("w:pPr")]
            new_content = [etree.tostring(n, method="c14n", exclusive=True) for n in p if n.tag != qn("w:pPr")]
            if old_content != new_content:
                raise ValueError(f"图片段落内容或尺寸变化：{before.element_id}")
        for old_i, new_i in zip(old_indices, new_indices, strict=True):
            if image_layout:
                audit.format_checks.append({"property": f"protected-run[{new_i}].text-format",
                                            "expected": None, "actual": None, "match": None,
                                            "excluded_reason": "纯图片 Run 无文字，字体继承随图片段落布局；图片 XML 保留"})
                continue
            for key in FORMAT_KEYS:
                wanted, actual = old_values[old_i][key], new_values[new_i][key]
                audit.format_checks.append({"property": f"protected-run[{new_i}].{key}", "expected": wanted,
                                           "actual": actual, "match": actual == wanted, "excluded_reason": None})
                if actual != wanted:
                    raise ValueError(f"受保护 Run 有效格式变化：{before.element_id} / {key}")
        old_base = external_text_baseline(original_p, source_resolver)
        if old_base is not None:
            new_base = external_text_baseline(p, output_resolver)
            if new_base is None:
                raise ValueError("公式或对象片段变化。")
            for key in FORMAT_KEYS:
                actual, wanted = new_base[key], old_base[key]
                audit.format_checks.append({"property": "external-text-base." + key, "actual": actual,
                                           "expected": wanted, "match": actual == wanted, "excluded_reason": None})
                if actual != wanted:
                    raise ValueError(f"公式或对象继承格式变化：{before.element_id} / {key}")
        if audit.style_application_status not in {"applied", "guarded"}:
            continue
        checks = audit.format_checks

        def check(prop: str, actual: Any, wanted: Any, reason: str | None = None) -> None:
            checks.append({"property": prop, "actual": actual, "expected": wanted,
                           "match": None if reason else actual == wanted, "excluded_reason": reason})

        target = expected[decision.role]
        check("pStyle", after.original_style_id, ROLE_TO_STYLE_ID[decision.role])
        for key in ("alignment", "outline_level", "keep_next", "page_break_before", "widow_control"):
            check(key, after.effective_format.get(key), target.get(key))
        for key in ("paragraph_indent", "paragraph_spacing"):
            for attr, wanted in target[key].items():
                numbered = key == "paragraph_indent" and bool(after.numbering_properties)
                check(key + "." + attr, after.effective_format[key].get(attr), wanted,
                      "编号相关缩进结构保留" if numbered else None)
        p = paragraphs[after.xml_path]
        eligible, guarded = _text_runs(p, field_runs)
        allowed = set(eligible)
        offset = 0
        run_values = after.effective_format["run_statistics"]["runs"]
        policy = policy_for_role(decision.role)
        for index, (run, values) in enumerate(zip(p.iter(qn("w:r")), run_values, strict=True)):
            role = decision.role
            if len(before.inline_segments) > 1 and offset >= before.inline_segments[1].start:
                role = before.inline_segments[1].role
            offset += values["text_length"]
            wanted_values = expected[role]["run_statistics"]["runs"][0]
            if not values["text_length"]:
                continue
            if run not in allowed:
                check(f"run[{index}]", "protected", "protected", "域、修订、公式和引用区域保持源格式")
                continue
            unresolved = index in audit.guarded_run_indices
            for key in ("font_slots", "font_size_pt", "font_size_cs_pt", "bold", "italic", "bold_cs", "italic_cs", "color"):
                if key == "color" and wanted_values[key] is None:
                    continue
                prop = {"bold": "b", "italic": "i", "bold_cs": "bCs", "italic_cs": "iCs"}.get(key, key)
                mixed = policy.run_properties[prop] == "conditional" if key in {"bold", "italic", "bold_cs", "italic_cs", "color"} else False
                conditional = mixed or role.endswith("-content") and key in {"bold", "italic", "bold_cs", "italic_cs", "color"}
                semantic = conditional and values[key] != wanted_values[key] and semantic_override(run, prop, ROLE_TO_STYLE_ID[role])
                hyperlink = key == "color" and any(a.tag == qn("w:hyperlink") for a in run.iterancestors())
                reason = "局部语义格式允许覆盖目标" if semantic else "超链接语义颜色保留" if hyperlink else "无法解析字符样式，保留源 Run" if unresolved else None
                check(f"run[{index}].{key}", values[key], wanted_values[key], reason)
        audit.effective_format_match = all(c["match"] is not False for c in checks)
        if guarded or any(c["excluded_reason"] for c in checks):
            audit.style_application_status = "guarded"
