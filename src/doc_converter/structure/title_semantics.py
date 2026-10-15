"""Versioned, local expression prototypes and bounded cover-role competition.

Scores describe expression structure, not language-model probabilities. A text
match never assigns a document role: front matter order and an independent body
boundary must corroborate it. Input adapters retain their own format weights.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from doc_converter.structure.numbering import numbering

PROTOTYPE_VERSION = "title-expressions/v1"
ROLES = ("document-title", "document-subtitle", "heading-1")
_SECTION = re.compile(
    r"^(?:(?:研究|实施|项目|建设|技术|工作|组织|总体|基本|主要|具体|适用|运行)?(?:背景|目的|目标|范围|方法|要求|措施|结论|结果|安排|保障|原则)"
    r"|研究方案|(?:报告|方案|计划)(?:编制|审查|实施|比选)(?:要求|方法|流程)?"
    r"|(?:introduction|background|methods?|results?|discussion|conclusions?|scope|requirements))$",
    re.I,
)
_LOCAL = re.compile(r"(?:编制要求|比选|方案比较|执行要求)$")
_PROSE = re.compile(
    r"[。！？!?；;.]$|应当|不得|本[章节段文](?:介绍|说明|讨论|规定|列出)|We (?:use|compare)\b", re.I
)
_EXCERPT = re.compile(r"节选|摘录|片段|excerpt|continued", re.I)
_FORMAL = re.compile(
    r"^(?:关于(?P<topic>.+?)(?:的通知|的意见|的决定)|(?P<object>.+?)(?:实施方案|研究报告|技术规范书|工作计划|分析报告|管理办法))$"
)
_THEME = (
    ("transition", re.compile(r"^从(.{2,})[走转]向(.{2,})$")),
    ("purpose-object", re.compile(r"^面向(.{2,})的(.{2,})$")),
    ("cause-object", re.compile(r"^(.{3,})(?:驱动|赋能|促进)(.{3,})$")),
    ("object-property", re.compile(r"^(.{4,})的(.{3,})$")),
    ("coordinate-topic", re.compile(r"^(.{4,})(?:与|及)(.{4,})$")),
    ("english-topic", re.compile(r"^(?:[A-Z][\w-]*\s+){1,}.*\b(?:and|of|for|in)\b.+", re.I)),
)
_VIEW = (
    ("case-scope", re.compile(r"^(?:以|以对)(.{2,})为(?:例|实践对象|观察窗口|研究对象|切入点)$")),
    ("basis-perspective", re.compile(r"^基于(.{2,})的(.{2,})$")),
    ("evidence-source", re.compile(r"^来自(.{2,})的(.{2,})(?:证据|观察|分析)$")),
    ("viewpoint", re.compile(r"^(.{2,})视角下的(.{2,})$")),
    (
        "english-evidence",
        re.compile(r"^(?:Evidence from|A case study of|An? .+ perspective on)\s+.+", re.I),
    ),
)


def semantic_profile(text: str) -> dict[str, Any]:
    """Three independent prototype scores, with slots and negative examples."""
    clean = re.sub(r"\s+", " ", text).strip().lstrip("—–- ")
    scores = dict.fromkeys(ROLES, 0)
    matches: list[dict[str, Any]] = []

    def add(role: str, points: int, prototype: str, slots: tuple[str, ...] = ()) -> None:
        scores[role] += points
        matches.append(
            {"role": role, "points": points, "prototype": prototype, "slots": list(slots)}
        )

    if not clean or len(clean) > 180 or _PROSE.search(clean):
        return {"version": PROTOTYPE_VERSION, "scores": scores, "matches": [], "prose": True}
    family, _, token = numbering(clean)
    content = clean[len(token or "") :].strip()
    if family:
        add("heading-1", 32, "chapter-number", (token or "", content))
    if _SECTION.fullmatch(content) or _LOCAL.search(content) or _EXCERPT.search(clean):
        add("heading-1", 44, "local-section-scope", (content,))
    formal = _FORMAL.fullmatch(clean)
    if formal and len(next(v for v in formal.groups() if v)) >= 4:
        add("document-title", 38, "topic-document-type", tuple(v for v in formal.groups() if v))
    for name, pattern in _THEME:
        m = pattern.fullmatch(clean)
        if m and len(clean) >= 10:
            add("document-title", 32, name, m.groups())
            break
    for name, pattern in _VIEW:
        m = pattern.fullmatch(clean)
        if m:
            add("document-subtitle", 38, name, m.groups())
            # Basis/viewpoint constructions can also be complete main themes.
            if name in {"basis-perspective", "viewpoint"}:
                add("document-title", 24, "complete-perspective-topic", m.groups())
            break
    if scores["heading-1"] >= 44 or family:
        add("document-title", -32, "numbered-or-local-counterexample", (content,))
        add("document-subtitle", -32, "numbered-or-local-counterexample", (content,))
    elif not any(scores.values()) and (
        8 <= len(clean) <= 60
        and len(re.findall(r"[\u4e00-\u9fff]", clean)) >= 8
        or 4 <= len(clean.split()) <= 12
    ):
        add("document-title", 14, "unmarked-topic-shape", (clean,))
    return {"version": PROTOTYPE_VERSION, "scores": scores, "matches": matches, "prose": False}


@dataclass(frozen=True)
class TitleParagraph:
    element_id: str
    text: str
    level: int = 0
    native_role: str | None = None
    blocked: bool = False
    metadata: bool = False
    centered: bool = False
    large: bool = False
    preface_boundary: bool = False


def _terms(text: str) -> set[str]:
    words = set(re.findall(r"[a-z]{3,}", text.lower()))
    chars = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    words.update(chars[i : i + 2] for i in range(len(chars) - 1))
    return words - {
        "研究",
        "管理",
        "方案",
        "报告",
        "基于",
        "实践",
        "分析",
        "and",
        "from",
        "the",
        "for",
    }


def select_title_area(
    paragraphs: list[TitleParagraph],
    *,
    title: str = "",
    subtitle: str = "",
) -> dict[str, Any]:
    """Compare cover/no-cover hypotheses in the first 12 nonempty paragraphs.

    A prose paragraph closes the cover window. This prevents semantic matches
    in actual body sections from inheriting document-level identity. A subtitle
    must follow a title and share content terms or an explicit scope/viewpoint
    relation; it is optional. Native Title/Subtitle anchors remain explicit.
    """
    window = [p for p in paragraphs if p.text.strip()][:12]
    profiles = {p.element_id: semantic_profile(p.text) for p in window}
    selected: dict[str, str] = {}
    audit: dict[str, Any] = {
        "version": PROTOTYPE_VERSION,
        "selected": selected,
        "hypotheses": [],
        "relations": [],
    }
    if not window:
        return audit
    first = window[0]
    first_profile = profiles[first.element_id]
    if first.blocked or first.metadata:
        return audit
    # A leading real chapter wins against a cover hypothesis; existing source
    # anchors are required, so ordinary short paragraphs are not promoted.
    if first.level == 1 and first_profile["scores"]["heading-1"] >= 44 and not first.native_role:
        selected[first.element_id] = "heading-1"
        audit["hypotheses"].append(
            {"ids": [first.element_id], "role": "heading-1", "reason": "anchored-local-section"}
        )
        return audit

    title_group: list[TitleParagraph] = []
    body_index: int | None = None
    # Independent next-section evidence: anchors or a common section expression
    # followed by prose. Cover recognition cannot depend on existing role guesses.
    for i, p in enumerate(window):
        profile = profiles[p.element_id]
        if p.blocked:
            break
        if i and p.preface_boundary:
            body_index = i
            break
        if profile["prose"] and not p.metadata:
            break
        if (
            i
            and (p.level or profile["scores"]["heading-1"] >= 44)
            and (numbering(p.text)[0] or profile["scores"]["heading-1"] >= 44)
            and not p.native_role
        ):
            body_index = i
            break
    native_title = first.native_role == "document-title"
    group_text = first.text
    # A grammatical continuation across two real paragraphs is one title area;
    # do not join two independent complete topics merely because both are early.
    if (
        len(window) > 1
        and re.search(r"(?:的|与|及|for|of)\s*$", first.text, re.I)
        and not window[1].blocked
    ):
        joined = first.text.rstrip() + window[1].text.lstrip()
        if semantic_profile(joined)["scores"]["document-title"] >= 26:
            title_group = window[:2]
            group_text = joined
    group_profile = semantic_profile(group_text)
    score = group_profile["scores"]["document-title"]
    complete_theme = score >= 26 and group_profile["scores"]["heading-1"] < 44
    paired_view = bool(
        len(window) > 1
        and profiles[window[1].element_id]["scores"]["document-subtitle"] >= 30
        and body_index is not None
        and body_index > 1
        and not (first.level and window[1].level > first.level)
    )
    supported_topic = score >= 14 and (paired_view or first.centered and first.large)
    native_parent = bool(
        body_index is not None and first.level and window[body_index].level > first.level
    )
    independent_body = (
        not native_parent
        or native_title
        or paired_view
        or len(title_group) > 1
        and not (first.level and title_group[1].level > first.level)
        or first.centered
        and first.large
    )
    # A topic expression alone cannot erase a genuine H1 owning H2 children.
    # A document-type expression is additional evidence only when the source
    # does not already describe that parent/child tree.
    if native_parent and not independent_body and complete_theme and first.level == 1:
        selected[first.element_id] = "heading-1"
    standalone = len(window) == len(title_group or [first])
    cover = (
        native_title
        or (complete_theme or supported_topic)
        and independent_body
        and (body_index is not None or standalone)
    )
    audit["hypotheses"].append(
        {
            "ids": [p.element_id for p in title_group or [first]],
            "role": "document-title",
            "semantic_score": score,
            "body_boundary": body_index,
            "native_parent_tree": native_parent,
            "accepted": bool(cover and not title),
        }
    )
    if cover and not title:
        title_group = title_group or [first]
        for p in title_group:
            selected[p.element_id] = "document-title"
        title = group_text
    elif not title:
        # No cover was established. Keep the current input-specific decision,
        # except a known section expression already handled above.
        if (
            first.level == 1
            and len(window) > 1
            and profiles[window[1].element_id]["prose"]
            and any(p.level == 1 for p in window[2:])
        ):
            selected[first.element_id] = "heading-1"
            audit["hypotheses"].append(
                {
                    "ids": [first.element_id],
                    "role": "heading-1",
                    "reason": "body-prose-and-peer-sections",
                }
            )
        return audit
    next_index = len(title_group)
    if subtitle or next_index >= len(window):
        return audit
    p = window[next_index]
    profile = profiles[p.element_id]
    if p.blocked or p.metadata or profile["prose"]:
        return audit
    overlap = sorted(_terms(title) & _terms(p.text))
    viewpoint = profile["scores"]["document-subtitle"] >= 30
    native_subtitle = p.native_role == "document-subtitle"
    relation = bool(overlap or viewpoint)
    # A bare thematic overlap (e.g. two chapter names sharing '物资') is weak;
    # require a scope/viewpoint expression or an explicit native Subtitle.
    accepted = (
        native_subtitle
        or viewpoint
        and relation
        and body_index is not None
        and next_index < body_index
    )
    audit["relations"].append(
        {
            "title_ids": [n.element_id for n in title_group],
            "subtitle_id": p.element_id,
            "shared_terms": overlap,
            "viewpoint": viewpoint,
            "accepted": bool(accepted),
        }
    )
    if accepted:
        selected[p.element_id] = "document-subtitle"
    return audit
