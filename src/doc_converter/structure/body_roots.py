"""Final body-root consistency, independent of input syntax and score weights.

Adapters provide selected paragraphs and immutable structure facts. This pass
never promotes a non-heading, invents a parent, or changes a numbering string.
Candidate trees remain evidence; final trees describe the selected output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from doc_converter.structure.numbering import numbering, ordinal

_INDEPENDENT = re.compile(
    r"^(?:(?:附录|附件)(?:[A-Za-zＡ-Ｚ\d一二三四五六七八九十]+)?(?:[\s：:、.]|$)"
    r"|(?:参考文献|参考资料|references?)\s*[:：]?$|appendix\b)",
    re.I,
)
_EXCERPT = re.compile(r"节选|摘录|片段|选段|部分章节|(?:excerpt|extract|continued)\b", re.I)
_OPENING = re.compile(
    r"^(?:总体要求|总则|概述|引言|前言|范围|适用范围|背景|项目背景|overview|introduction|scope)$",
    re.I,
)


def is_body_opening(text: str) -> bool:
    """A section label, rather than a cover title, including a numbered label."""
    _, _, token = numbering(text.strip())
    return bool(_OPENING.fullmatch(text.strip()[len(token or "") :].strip()))


@dataclass(frozen=True)
class FinalParagraph:
    element_id: str
    text: str
    role: str
    mapped: bool = True
    source_level: int | None = None
    facts: dict[str, Any] = field(default_factory=dict)


def _tree(nodes: list[FinalParagraph], levels: dict[str, int]) -> list[dict[str, Any]]:
    stack: list[dict[str, Any]] = []
    result = []
    for n in nodes:
        level = levels[n.element_id]
        if n.facts.get("hierarchy_reset_marker"):
            stack.clear()
        while stack and stack[-1]["effective_level"] >= level:
            stack.pop()
        item = {
            "element_id": n.element_id,
            "effective_level": level,
            "parent_id": stack[-1]["element_id"] if stack else None,
            "regime": n.facts.get("hierarchy_regime_id"),
        }
        result.append(item)
        stack.append(item)
    return result


def normalize_body_roots(
    paragraphs: list[FinalParagraph],
    *,
    title: str = "",
) -> tuple[dict[str, int], dict[str, Any]]:
    """Return final levels and an audit; require positive whole-body evidence.

    Independent back matter is outside the body. Missing numbered/virtual
    parents and conflicting sources veto an offset. A native unnumbered tree
    may retain its gaps when the candidate resolver compressed them, provided
    its real parent edges agree with final decisions. This is gap restoration,
    not a reclassification or a second schema resolver.
    """
    body: list[FinalParagraph] = []
    for p in paragraphs:
        if _INDEPENDENT.match(p.text.strip()) and (
            p.role.startswith("heading-") or p.role == "reference-heading"
        ):
            break
        if p.facts.get("region") != "postface":
            body.append(p)
    nodes = [p for p in body if re.fullmatch(r"heading-[1-6]", p.role)]
    original = {p.element_id: int(p.role[-1]) for p in nodes}
    audit: dict[str, Any] = {
        "status": "preserved",
        "reason": "no-body-headings",
        "offset": 0,
        "root_level_before": min(original.values(), default=None),
        "affected_ids": [],
        "root_ids": [],
        "trees": [],
        "before_tree": _tree(nodes, original),
        "final_tree": _tree(nodes, original),
    }

    def preserve(reason: str) -> tuple[dict[str, int], dict[str, Any]]:
        audit["reason"] = reason
        return original, audit

    if not nodes:
        return preserve("no-body-headings")
    front = [title, nodes[0].text] + [
        p.text for p in body if p.role in {"document-title", "document-subtitle"}
    ]
    if any(_EXCERPT.search(t) for t in front):
        # The DOCX candidate resolver may already have compressed a native
        # excerpt. Restore only corroborated mapped anchors with the same
        # parent edges, so 'preserved' really means preserving the excerpt.
        if all(n.mapped and n.source_level for n in nodes):
            source = {n.element_id: int(n.source_level or 1) for n in nodes}
            source_tree = _tree(nodes, source)
            if [p["parent_id"] for p in source_tree] == [
                p["parent_id"] for p in audit["before_tree"]
            ]:
                audit.update(
                    final_tree=source_tree,
                    affected_ids=[k for k in source if source[k] != original[k]],
                )
                audit["reason"] = "explicit-excerpt"
                return source, audit
        return preserve("explicit-excerpt")
    if any(not n.mapped for n in nodes):
        return preserve("unmapped-heading")
    # A preserved source heading/unknown candidate may supply a missing root;
    # never shift the selected subset around it.
    if any(not p.mapped and (p.source_level or p.facts.get("heading_candidate")) for p in body):
        return preserve("protected-structural-node")
    for n in nodes:
        f = n.facts
        gap_only = (
            n.source_level
            and f.get("local_hierarchy_warning") == "hierarchy_jump"
            and (not f.get("numbering_family") or f.get("reliable_explicit_anchor"))
        )
        if (
            f.get("recovery_virtual_hint")
            or f.get("parent_resolution_type") == "inferred_virtual_parent"
            or f.get("recovery_force_preserve")
            or f.get("source_defect_type")
            in {"broken_numbering_sequence", "missing_parent_heading"}
            and not gap_only
        ):
            return preserve("missing-virtual-or-conflicting-parent")
    levels = dict(original)
    native = {n.element_id: n.source_level for n in nodes}
    native_gaps = False
    if all(native.values()) and not any(
        n.facts.get("recovered_outline_level") or n.facts.get("recovered_heading_family")
        for n in nodes
    ):
        source_levels = {k: int(v) for k, v in native.items() if v is not None}
        source_tree = _tree(nodes, source_levels)
        same_edges = [p["parent_id"] for p in source_tree] == [
            p["parent_id"] for p in audit["before_tree"]
        ]
        outline_peers = [p for p in source_tree if p["parent_id"] is None]
        direct_outline_tree = (
            any(n.facts.get("explicit_outline_anchor") for n in nodes)
            and all(
                (n.facts.get("explicit_outline_anchor") or n.facts.get("native_heading_level"))
                and not n.facts.get("numbering_family")
                for n in nodes
            )
            and len(outline_peers) >= 2
            and len({p["effective_level"] for p in outline_peers}) == 1
        )
        if same_edges or direct_outline_tree:
            levels = source_levels
            native_gaps = levels != original
            audit["explicit_outline_tree_recovery"] = not same_edges
    tree = _tree(nodes, levels)
    roots = [n for n in tree if n["parent_id"] is None]
    audit.update(
        root_ids=[n["element_id"] for n in roots],
        source_root_level=min(levels.values()),
        native_gap_restoration=native_gaps,
    )
    root_levels = {n["effective_level"] for n in roots}
    if len(root_levels) != 1:
        return preserve("independent-roots-at-different-levels")
    by_id = {n.element_id: n for n in nodes}
    root_nodes = [by_id[n["element_id"]] for n in roots]
    for n in root_nodes:
        path = n.facts.get("numbering_path") or ordinal(numbering(n.text)[2])
        if len(path) > 1 or path and path[0] != 1 and n is root_nodes[0]:
            # A document beginning at a later named chapter is a chapter
            # excerpt even without a literal '节选' label. Unlike a bare
            # procurement item '5.', its chapter scope is explicit evidence.
            if (
                n.facts.get("numbering_family") == "CHAPTER"
                and len(path) == 1
                and path[0] > 1
                and min(levels.values()) > 1
            ):
                audit.update(
                    reason="later-chapter-excerpt",
                    final_tree=tree,
                    affected_ids=[k for k in levels if levels[k] != original[k]],
                )
                return levels, audit
            return preserve("partial-numbered-scope")
        if n.facts.get("numbering_family") in {
            "CN_BRACKET",
            "ARABIC_BRACKET",
            "SECTION",
            "CIRCLED",
        }:
            return preserve("subsection-root-without-parent")
    start = min(levels.values())
    if start == 1:
        # An existing source H1 forbids rebasing, but keep native edge gaps.
        final = levels if native_gaps else original
        audit.update(reason="existing-body-h1", final_tree=_tree(nodes, final))
    else:
        has_body = any(p.role == "body-paragraph" and p.text.strip() for p in body)
        child_ids = {p["parent_id"] for p in tree if p["parent_id"]}
        paths = [n.facts.get("numbering_path") or ordinal(numbering(n.text)[2]) for n in root_nodes]
        sequence = (
            len(paths) >= 2
            and all(len(p) == 1 for p in paths)
            and [p[0] for p in paths] == list(range(1, len(paths) + 1))
        )
        opening = is_body_opening(root_nodes[0].text)
        has_title = bool(title or any(p.role == "document-title" for p in body))
        complete = has_body and (
            opening
            and bool(child_ids or len(roots) >= 2)
            or len(roots) >= 2
            and (sequence or has_title or bool(child_ids))
        )
        if not complete:
            return preserve("insufficient-whole-body-evidence")
        final = {k: v - start + 1 for k, v in levels.items()}
        audit.update(
            reason="coherent-complete-body-offset",
            offset=start - 1,
            evidence={
                "opening": opening,
                "root_sequence": sequence,
                "independent_title": has_title,
                "has_child_tree": bool(child_ids),
            },
            final_tree=_tree(nodes, final),
        )
    changed = [k for k in original if final[k] != original[k]]
    audit.update(
        status="normalized" if changed else "unchanged",
        affected_ids=changed,
        trees=[{"root_id": r["element_id"], "offset": audit["offset"]} for r in roots],
    )
    return final, audit
