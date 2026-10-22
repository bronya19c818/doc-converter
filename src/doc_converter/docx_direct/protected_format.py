"""Protect effective inherited text formatting, as well as original XML nodes."""

from copy import deepcopy
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from doc_converter.docx_direct.effective_format import EffectiveFormatResolver
from doc_converter.docx_direct.formatting import _GUARDED_ANCESTORS, _GUARDED_RUN_CONTENT
from doc_converter.docx_direct.pictures import is_inline_picture_run

FORMAT_KEYS = ("font_slots", "font_size_pt", "font_size_cs_pt", "bold", "bold_cs", "italic", "italic_cs", "color", "underline", "highlight", "vert_align")


def external_text_baseline(paragraph: Any, resolver: EffectiveFormatResolver) -> dict[str, Any] | None:
    if paragraph.find(".//" + qn("m:oMath")) is None and paragraph.find(".//" + qn("w:object")) is None:
        return None
    probe = deepcopy(paragraph)
    for child in list(probe):
        if child.tag != qn("w:pPr"):
            probe.remove(child)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "base"
    run.append(text)
    probe.append(run)
    return resolver.resolve_paragraph(probe, paragraph_style_id=None)["run_statistics"]["runs"][0]


def protected_run_indices(paragraph: Any, field_runs: frozenset[Any]) -> set[int]:
    result = set()
    for index, run in enumerate(paragraph.iter(qn("w:r"))):
        tags = {n.tag.rsplit("}", 1)[-1] for n in run.iter() if isinstance(n.tag, str)}
        ancestors = {n.tag.rsplit("}", 1)[-1] for n in run.iterancestors() if n is not paragraph}
        if run in field_runs or tags & _GUARDED_RUN_CONTENT or ancestors & _GUARDED_ANCESTORS:
            result.add(index)
    return result


def protected_format_matches(
    before: Any, after: Any, source_resolver: EffectiveFormatResolver,
    output_resolver: EffectiveFormatResolver, field_runs: frozenset[Any],
    *, allow_picture_run_inheritance_change: bool = False,
) -> bool:
    indices = protected_run_indices(before, field_runs)
    if allow_picture_run_inheritance_change:
        # Picture-only runs have no text; their line-box inheritance follows image layout.
        indices -= {i for i, run in enumerate(before.iter(qn("w:r")))
                    if run not in field_runs and is_inline_picture_run(run)}
    has_external_text = before.find(".//" + qn("m:oMath")) is not None or before.find(".//" + qn("w:object")) is not None
    if not indices and not has_external_text:
        return True
    old = source_resolver.resolve_paragraph(before, paragraph_style_id=None)
    new = output_resolver.resolve_paragraph(after, paragraph_style_id=None)
    old_runs, new_runs = old["run_statistics"]["runs"], new["run_statistics"]["runs"]
    if len(old_runs) != len(new_runs):
        # Inline splitting is handled by separate stable protected-run matching
        # in post-verification; preflight always has identical node topology.
        return False
    if any(any(old_runs[i][k] != new_runs[i][k] for k in FORMAT_KEYS) for i in indices):
        return False
    if has_external_text:
        # Math/OLE may have text outside w:r; avoid changing inherited base fonts.
        old_base = external_text_baseline(before, source_resolver)
        new_base = external_text_baseline(after, output_resolver)
        if old_base is None or new_base is None or any(old_base[k] != new_base[k] for k in FORMAT_KEYS):
            return False
    return True


def guarded_style_updates(
    document_root: Any, source_styles: Any, candidate_styles: Any, changed: set[str], field_runs: frozenset[Any],
) -> set[str]:
    source = EffectiveFormatResolver(source_styles, structural_guard=True)
    candidate = EffectiveFormatResolver(candidate_styles, structural_guard=True)
    definitions = {s.get(qn("w:styleId")): s for s in source_styles.findall(qn("w:style"))}
    blocked: set[str] = set()
    for p in document_root.iter(qn("w:p")):
        if protected_format_matches(p, p, source, candidate, field_runs):
            continue
        ids = [n.get(qn("w:val")) for n in p.iter() if n.tag in {qn("w:pStyle"), qn("w:rStyle")}]
        for current in ids:
            visited: set[str] = set()
            while current and current not in visited and len(visited) < 64:
                visited.add(current)
                if current in changed:
                    blocked.add(current)
                style = definitions.get(current)
                parent = style.find(qn("w:basedOn")) if style is not None else None
                current = parent.get(qn("w:val")) if parent is not None else None
    return blocked
