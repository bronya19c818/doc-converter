"""Split only plain text runs at explicit source-label boundaries."""

from copy import deepcopy
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from doc_converter.docx_direct.formatting import _text_runs
from doc_converter.docx_direct.model import InlineSegment


def prepare_inline_runs(
    paragraph: Any, segments: list[InlineSegment], field_runs: frozenset[Any], *, apply: bool = False,
) -> tuple[frozenset[Any], frozenset[Any]] | None:
    """Preflight before paragraph mutation; guarded label boundaries preserve all."""
    if not segments:
        return None
    boundary = segments[0].end
    eligible, _ = _text_runs(paragraph, field_runs)
    safe = set(eligible)
    label: set[Any] = set()
    content: set[Any] = set()
    offset = 0
    for run in list(paragraph.iter(qn("w:r"))):
        text = "".join((n.text or "") if n.tag in {qn("w:t"), qn("w:delText")}
                       else "\t" if n.tag == qn("w:tab") else "\n" if n.tag == qn("w:br")
                       else "" for n in run.iter())
        end = offset + len(text)
        if offset < boundary and text and (run not in safe or run.getparent() is not paragraph):
            return None
        if offset < boundary < end:
            if run.getparent() is not paragraph or any(n.tag not in {qn("w:rPr"), qn("w:t")} for n in run):
                return None
            if apply:
                left, right = deepcopy(run), deepcopy(run)
                for part, value in ((left, text[:boundary-offset]), (right, text[boundary-offset:])):
                    for n in list(part.findall(qn("w:t"))):
                        part.remove(n)
                    t = OxmlElement("w:t")
                    t.text = value
                    if value.startswith(" ") or value.endswith(" "):
                        t.set(qn("xml:space"), "preserve")
                    part.append(t)
                index = paragraph.index(run)
                paragraph.remove(run)
                paragraph.insert(index, left)
                paragraph.insert(index + 1, right)
                label.add(left)
                content.add(right)
        elif end <= boundary:
            label.add(run)
        else:
            content.add(run)
        offset = end
    # Text hidden in unsupported containers cannot be assigned by these offsets.
    if offset != segments[-1].end:
        return None
    return frozenset(label), frozenset(content)
