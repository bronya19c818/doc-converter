"""Paragraph/run policy execution with conservative structural boundaries."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from doc_converter.docx_direct.character_styles import CharacterStyleProjector
from doc_converter.docx_direct.model import PropertyDecision, TransformationAudit
from doc_converter.docx_direct.transformation_policy import (
    BODY_MIXED_POLICY,
    TransformationPolicy,
)

TEXT_TAGS = {qn("w:t"), qn("w:delText")}
_GUARDED_ANCESTORS = {
    "fldSimple",
    "ins",
    "del",
    "moveFrom",
    "moveTo",
    "drawing",
    "pict",
    "object",
    "oMath",
    "oMathPara",
}
_GUARDED_RUN_CONTENT = {
    "fldChar",
    "instrText",
    "footnoteReference",
    "endnoteReference",
    "drawing",
    "pict",
    "object",
    "oMath",
    "oMathPara",
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _record(
    audit: TransformationAudit,
    operation: Literal["removed", "preserved", "skipped"],
    property_name: str,
    level: Literal["paragraph", "run", "character-style", "structure"],
    mode: str,
    reason: str,
    count: int = 1,
) -> None:
    if not count:
        return
    records: list[PropertyDecision] = getattr(audit, operation + "_properties")
    existing = next(
        (
            r
            for r in records
            if (r.property, r.level, r.mode, r.reason) == (property_name, level, mode, reason)
        ),
        None,
    )
    if existing:
        existing.count += count
    else:
        records.append(
            PropertyDecision(
                property=property_name, level=level, mode=mode, reason=reason, count=count
            )
        )


def begin_policy_audit(paragraph: Any, policy: TransformationPolicy) -> TransformationAudit:
    structures = Counter(
        _local(n.tag)
        for n in paragraph.iter()
        if isinstance(n.tag, str) and _local(n.tag) in policy.protected_structures
    )
    safety: Literal["safe", "guarded", "preserve"] = (
        "preserve" if policy.family == "preserve" else "guarded" if structures else "safe"
    )
    audit = TransformationAudit(
        policy_name=policy.name, policy_family=policy.family, transform_safety=safety
    )
    for name, count in sorted(structures.items()):
        _record(
            audit,
            "preserved",
            name,
            "structure",
            "preserve",
            "结构绝对保留，不进入格式删除或重建",
            count,
        )
    return audit


def apply_paragraph_policy(
    paragraph: Any,
    policy: TransformationPolicy,
    audit: TransformationAudit,
    *,
    target_style: str | None,
) -> dict[str, int]:
    """Remove only explicitly style-controlled paragraph overrides."""
    if policy.family == "preserve":
        _record(
            audit, "skipped", "paragraph", "paragraph", "preserve", "角色或 action 不允许视觉重写"
        )
        return {}
    properties = paragraph.find(qn("w:pPr"))
    if properties is None:
        properties = OxmlElement("w:pPr")
        paragraph.insert(0, properties)
    if target_style is not None:
        style = properties.find(qn("w:pStyle"))
        if style is None:
            style = OxmlElement("w:pStyle")
            properties.insert(0, style)
        style.set(qn("w:val"), target_style)
    removed: dict[str, int] = {}
    for rule in policy.paragraph_rules:
        if rule.property == "pStyle":
            continue
        nodes = properties.findall(qn("w:" + rule.property))
        if not nodes:
            continue
        numbering_indent = rule.property == "ind" and properties.find(qn("w:numPr")) is not None
        if rule.mode == "preserve" or numbering_indent:
            reason = "编号/列表相关缩进保留" if numbering_indent else "策略保留该段落属性"
            _record(audit, "preserved", rule.property, "paragraph", rule.mode, reason, len(nodes))
        else:
            for node in nodes:
                properties.remove(node)
            removed[rule.property] = len(nodes)
            _record(
                audit,
                "removed",
                rule.property,
                "paragraph",
                rule.mode,
                "清除源段落覆盖，由目标段落样式接管",
                len(nodes),
            )
    mark = properties.find(qn("w:rPr"))
    if mark is not None:
        for rule in policy.run_rules:
            if rule.mode not in {"replace", "discard"}:
                continue
            for node in mark.findall(qn("w:" + rule.property)):
                mark.remove(node)
                _record(
                    audit,
                    "removed",
                    rule.property,
                    "paragraph",
                    rule.mode,
                    "清除段落标记的基础视觉覆盖",
                )
    return removed


def protected_field_runs(root: Any) -> frozenset[Any]:
    """Track complex fields across paragraph boundaries in document order."""
    protected: set[Any] = set()
    depth = 0
    for run in root.iter(qn("w:r")):
        guarded = depth > 0
        for char in run.iter(qn("w:fldChar")):
            guarded = True
            kind = char.get(qn("w:fldCharType"))
            if kind == "begin":
                depth += 1
            elif kind == "end":
                depth = max(0, depth - 1)
        if guarded:
            protected.add(run)
    return frozenset(protected)


def _text_runs(
    paragraph: Any, field_runs: frozenset[Any] = frozenset()
) -> tuple[list[Any], list[Any]]:
    eligible: list[Any] = []
    guarded: list[Any] = []
    field_depth = 0
    for run in paragraph.iter(qn("w:r")):
        local_tags = {_local(n.tag) for n in run.iter() if isinstance(n.tag, str)}
        ancestry = {
            _local(a.tag)
            for a in run.iterancestors()
            if a is not paragraph and isinstance(a.tag, str)
        }
        is_guarded = (
            run in field_runs
            or field_depth > 0
            or bool(local_tags & _GUARDED_RUN_CONTENT)
            or bool(ancestry & _GUARDED_ANCESTORS)
        )
        for char in run.iter(qn("w:fldChar")):
            kind = char.get(qn("w:fldCharType"))
            if kind == "begin":
                field_depth += 1
            elif kind == "end":
                field_depth = max(0, field_depth - 1)
        if not any(n.tag in TEXT_TAGS and n.text for n in run.iter()):
            continue
        (guarded if is_guarded else eligible).append(run)
    return eligible, guarded


def _property(run: Any, tag: str) -> Any | None:
    properties = run.find(qn("w:rPr"))
    return properties.find(qn("w:" + tag)) if properties is not None else None


def apply_run_policy(
    paragraph: Any,
    policy: TransformationPolicy,
    audit: TransformationAudit,
    *,
    projector: CharacterStyleProjector | None = None,
    neutral_character_styles: dict[str, frozenset[str]] | None = None,
    field_runs: frozenset[Any] = frozenset(),
) -> dict[str, int]:
    """Normalize ordinary text, preserving protected regions and local semantics."""
    if policy.family == "preserve":
        _record(audit, "skipped", "runs", "run", "preserve", "角色或 action 不允许视觉重写")
        return {}
    runs, guarded = _text_runs(paragraph, field_runs)
    if guarded:
        audit.transform_safety = "guarded"
        _record(
            audit,
            "skipped",
            "protected-text-runs",
            "run",
            "preserve",
            "域结果、修订、公式和引用相关文字保持原样",
            len(guarded),
        )
    removed: Counter[str] = Counter()
    neutral_character_styles = neutral_character_styles or {}
    conditional: set[str] = set()
    for rule in policy.run_rules:
        if rule.mode != "conditional" or rule.property == "rStyle" or not runs:
            continue
        values = [_property(r, rule.property) for r in runs]
        uniform = (
            not guarded
            and all(n is not None for n in values)
            and len({tuple(sorted(n.attrib.items())) for n in values if n is not None}) == 1
        )
        has_semantic_style = any(_property(r, "rStyle") is not None for r in runs)
        hyperlinks = rule.property in {"color", "u", "highlight"} and any(
            any(_local(a.tag) == "hyperlink" for a in r.iterancestors()) for r in runs
        )
        if uniform and not has_semantic_style and not hyperlinks:
            conditional.add(rule.property)
    stripped = frozenset(r.property for r in policy.run_rules if r.mode in {"replace", "discard"})
    for run in runs:
        properties = run.find(qn("w:rPr"))
        if properties is None:
            continue
        style = _property(run, "rStyle")
        style_id = style.get(qn("w:val")) if style is not None else None
        if style_id and projector is not None:
            projected = projector.project(style_id, stripped)
            if projected is None:
                audit.transform_safety = "guarded"
                _record(
                    audit,
                    "skipped",
                    "rStyle",
                    "character-style",
                    "conditional",
                    "字符样式缺失、循环或无法安全解析，保留该 run 的源格式",
                )
                continue
            if projected != style_id and style is not None:
                style.set(qn("w:val"), projected)
                for property_name, count in projector.removed_properties(
                    style_id, stripped
                ).items():
                    _record(
                        audit,
                        "removed",
                        property_name,
                        "character-style",
                        policy.run_properties[property_name],
                        "派生字符样式过滤此属性的源继承覆盖，原字符样式定义保留",
                        count,
                    )
            _record(
                audit,
                "preserved",
                "rStyle",
                "character-style",
                "conditional",
                "保留字符样式语义；原字符样式定义不修改",
            )
        for rule in policy.run_rules:
            if rule.property == "rStyle":
                continue
            nodes = properties.findall(qn("w:" + rule.property))
            if not nodes:
                continue
            replace = rule.mode in {"replace", "discard"} or rule.property in conditional
            unresolved_style = (
                style_id
                and projector is None
                and rule.property in stripped
                and style_id not in neutral_character_styles.get(rule.property, frozenset())
            )
            if unresolved_style:
                _record(
                    audit,
                    "skipped",
                    rule.property,
                    "run",
                    rule.mode,
                    "兼容入口没有可写样式上下文，保守保留非中性字符样式覆盖",
                    len(nodes),
                )
                audit.transform_safety = "guarded"
            elif replace:
                for node in nodes:
                    properties.remove(node)
                removed[rule.property] += len(nodes)
                reason = (
                    "全段直接格式一致，清除基础视觉覆盖"
                    if rule.mode == "conditional"
                    else "清除源字符视觉覆盖，由目标角色样式接管"
                )
                _record(audit, "removed", rule.property, "run", rule.mode, reason, len(nodes))
            else:
                _record(
                    audit,
                    "preserved",
                    rule.property,
                    "run",
                    rule.mode,
                    "保留局部语义格式、上下标或证据不足的视觉属性",
                    len(nodes),
                )
    return dict(removed)


def clean_uniform_direct_formatting(
    paragraph: Any,
    *,
    neutral_character_styles: dict[str, frozenset[str]] | None = None,
) -> dict[str, int]:
    """Compatibility wrapper for the former mixed-body run cleanup entry point."""
    audit = begin_policy_audit(paragraph, BODY_MIXED_POLICY)
    return apply_run_policy(
        paragraph, BODY_MIXED_POLICY, audit, neutral_character_styles=neutral_character_styles
    )
