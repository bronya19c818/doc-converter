"""Heading qualification, hierarchy schemas, compression and auditable trees.

Only additive role evidence leaves this module. It never selects decisions,
maps styles or edits Word XML.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from doc_converter.docx_direct.manual_sequences import (
    CHINESE_ORDER,
    extract_sequence_evidence,
    structure_safe,
)
from doc_converter.docx_direct.model import RoleCandidate
from doc_converter.docx_direct.scoring import ScoringConfig, contribute
from doc_converter.docx_direct.source_structure_recovery import (
    heading_family,
    heading_outline,
    heading_path,
    prepare_source_recovery,
)


@dataclass(frozen=True)
class HierarchySchema:
    name: str
    theoretical_order: tuple[str, ...]


SCHEMAS = (
    HierarchySchema("chinese_business", CHINESE_ORDER),
    HierarchySchema("chinese_report", CHINESE_ORDER[2:6]),
    HierarchySchema("decimal_technical", ("DECIMAL-1", "DECIMAL-2", "DECIMAL-3", "DECIMAL-4")),
)


@dataclass
class HierarchyRegime:
    regime_id: str
    start_index: int
    end_index: int
    schema_name: str = "chinese_report"
    parent_id: str | None = None
    parent_native_level: int | None = None
    parent_numbering_path: tuple[int, ...] = ()
    child_root_family: str | None = None
    last_root_ordinal: int | None = None
    active_families: list[str] = field(default_factory=list)
    compressed_levels: dict[str, int] = field(default_factory=dict)
    base_level: int | None = 0
    effective_levels: dict[str, int | None] = field(default_factory=dict)
    effective_level_variants: dict[str, list[int]] = field(default_factory=dict)
    indices: list[int] = field(default_factory=list)


@dataclass
class HeadingNode:
    element_id: str
    text: str
    family: str | None
    effective_level: int | None
    parent_id: str | None
    children: list[str]
    schema: str
    regime: str
    warnings: list[str] = field(default_factory=list)
    source_native_level: int | None = None


def _qualified(features: list[dict[str, Any]]) -> None:
    peers: defaultdict[tuple[int, str], int] = defaultdict(int)
    families: defaultdict[int, set[str]] = defaultdict(set)
    scope = 0
    pending_reset = False
    chapter_seen = False
    for f in features:
        if pending_reset or f["hierarchy_reset_marker"] or (
            f["numbering_family"] == "CHAPTER" and f["numbering_ordinal"] == 1 and chapter_seen
        ):
            scope += 1
        pending_reset = f["has_section_break"]
        chapter_seen |= f["numbering_family"] == "CHAPTER"
        f["heading_qualification_scope"] = scope
        safe = structure_safe(f) and not f["body_sentence"] and f["short_text"] \
            and not f["manual_sequence_candidate"] and not f["manual_sequence_uncertain"]
        f["heading_candidate"] = False
        if safe and f["numbering_family"]:
            peers[scope, f["numbering_family"]] += 1
            families[scope].add(f["numbering_family"])
    for f in features:
        safe = structure_safe(f) and not f["body_sentence"] and f["short_text"] \
            and not f["manual_sequence_candidate"] and not f["manual_sequence_uncertain"]
        anchor = f["native_heading_level"] is not None or (
            isinstance(f["outline_level"], int) and 0 <= f["outline_level"] <= 5 and not f["based_on_heading"]
        )
        scope = f["heading_qualification_scope"]
        f["heading_candidate"] = bool(safe and (
            anchor or f["relative_heading_marker"] or f["hierarchy_reset_marker"]
            or f["numbering_family"] and f["has_child_content_before_next_peer"] and (
                f["numbering_family"] in {"CHAPTER", "SECTION"} or len(families[scope]) >= 2
                or peers[scope, f["numbering_family"]] >= 2
            )
        ))


def _regimes(features: list[dict[str, Any]]) -> list[HierarchyRegime]:
    regimes = [HierarchyRegime("regime-1", 0, len(features))]
    stack = [regimes[0]]
    previous: dict[str, Any] | None = None
    last_numeric: dict[str, Any] | None = None
    chapter_seen = False
    pending_reset = False
    root_has_chinese = False
    root_min_native: int | None = None
    next_heading: list[dict[str, Any] | None] = [None] * len(features)
    following = None
    for i in range(len(features) - 1, -1, -1):
        next_heading[i] = following
        if features[i]["heading_candidate"]:
            following = features[i]
    for i, f in enumerate(features):
        following = next_heading[i]
        stable_decimal_reset = bool(
            f["heading_candidate"] and f["bare_numeric_root"] and f["numbering_ordinal"] == 1
            and following and heading_family(following) == "DECIMAL"
            and heading_path(following)[:1] == heading_path(f)
            and root_has_chinese
        )
        reset = pending_reset or f["hierarchy_reset_marker"] or (
            f["heading_candidate"] and heading_family(f) == "CHAPTER"
            and f["numbering_ordinal"] == 1 and chapter_seen
        ) or stable_decimal_reset
        pending_reset = f["has_section_break"]
        if reset and i:
            for r in stack:
                r.end_index = i
            r = HierarchyRegime(f"regime-{len(regimes) + 1}", i, len(features))
            regimes.append(r)
            stack = [r]
            previous = None
            last_numeric = None
            root_has_chinese = False
            root_min_native = None
        if not f["heading_candidate"]:
            continue
        if heading_family(f) == "CHAPTER":
            chapter_seen = True
        native = heading_outline(f)
        previous_outline = heading_outline(previous) if previous is not None else None
        while len(stack) > 1:
            scope = stack[-1]
            native_close = native is not None and scope.parent_native_level is not None and native <= scope.parent_native_level
            path = heading_path(f)
            nested_restart = bool(previous and native is None and f["numbering_ordinal"] == 1
                                  and heading_family(f) == heading_family(previous) == "ARABIC_ENUM"
                                  and previous_outline is not None
                                  and scope.parent_native_level is not None
                                  and previous_outline > scope.parent_native_level)
            continues_child_series = native is None and heading_family(f) == scope.child_root_family \
                and scope.last_root_ordinal is not None and f["numbering_ordinal"] == scope.last_root_ordinal + 1
            path_close = bool(scope.parent_numbering_path and heading_family(f) in {"DECIMAL", "ARABIC_ENUM"}
                              and not nested_restart and not continues_child_series
                              and (native is None or scope.parent_native_level is None or native <= scope.parent_native_level)
                              and (len(path) <= len(scope.parent_numbering_path)
                                   or path[:len(scope.parent_numbering_path)] != scope.parent_numbering_path))
            if not native_close and not path_close:
                break
            stack.pop().end_index = i
        starts_below_native_container = bool(previous and heading_family(previous) is None
                                              and not previous["relative_heading_marker"]
                                              and previous_outline is not None
                                              and native == previous_outline + 1)
        if previous is not None and heading_family(f) and (f["numbering_ordinal"] == 1 or starts_below_native_container):
            pn = heading_outline(previous)
            has_native_parent = pn is not None and root_min_native is not None and root_min_native < pn
            parent_container = heading_family(previous) is None and pn is not None and pn >= 2 and has_native_parent \
                and (native is None or native > pn)
            nested_series = pn is not None and native == pn + 1 and heading_path(f)[:1] != heading_path(previous)[:1]
            if previous["relative_heading_marker"] and pn == 1:
                nested_series = False
            numeric_parent = heading_family(previous) == "DECIMAL" and native is not None \
                and heading_family(f) != "DECIMAL" and native > len(heading_path(previous))
            restarted_native_series = heading_family(previous) == "ARABIC_ENUM" \
                and heading_family(f) == "ARABIC_ENUM" and pn is not None and native is None
            anchored_decimal_child = heading_family(previous) == "DECIMAL" and pn is not None \
                and heading_family(f) == "ARABIC_ENUM" and native is None \
                and f["has_child_content_before_next_peer"]
            if parent_container or nested_series or numeric_parent or restarted_native_series or anchored_decimal_child or starts_below_native_container:
                ancestor_path = heading_path(previous) if numeric_parent or anchored_decimal_child else ()
                numeric_outline = heading_outline(last_numeric) if last_numeric is not None else None
                if not ancestor_path and parent_container and last_numeric is not None \
                        and numeric_outline is not None and pn is not None and numeric_outline < pn:
                    ancestor_path = heading_path(last_numeric)
                r = HierarchyRegime(f"regime-{len(regimes) + 1}", i, len(features),
                                    parent_id=previous["element_id"], parent_native_level=pn or ((native or 1) - 1),
                                    parent_numbering_path=ancestor_path,
                                    child_root_family=heading_family(f))
                regimes.append(r)
                stack.append(r)
        stack[-1].indices.append(i)
        if heading_family(f) == stack[-1].child_root_family:
            stack[-1].last_root_ordinal = f["numbering_ordinal"]
        if len(stack) == 1:
            root_has_chinese |= heading_family(f) in {"CHAPTER", "SECTION", "CN_ENUM", "CN_BRACKET"}
            if native is not None:
                root_min_native = native if root_min_native is None else min(root_min_native, native)
        f["hierarchy_regime_id"] = stack[-1].regime_id
        previous = f
        if heading_family(f) in {"ARABIC_ENUM", "DECIMAL"}:
            last_numeric = f
    for r in regimes:
        members = [features[i] for i in r.indices]
        families = {heading_family(f) for f in members if heading_family(f)}
        decimal = "DECIMAL" in families and not families.intersection({"CHAPTER", "SECTION", "CN_ENUM", "CN_BRACKET"})
        r.schema_name = "decimal_technical" if decimal else (
            "chinese_business" if families.intersection({"CHAPTER", "SECTION", "CIRCLED"}) else "chinese_report"
        )
        if decimal:
            depths = sorted({len(heading_path(f)) for f in members if heading_path(f)})
            r.active_families = [f"DECIMAL-{d}" for d in depths]
            r.compressed_levels = {f"DECIMAL-{d}": d for d in depths}
        else:
            schema = next(s for s in SCHEMAS if s.name == r.schema_name)
            r.active_families = [family for family in schema.theoretical_order if family in families]
            r.compressed_levels = {family: level for level, family in enumerate(r.active_families, 1)}
    return regimes


def resolve_hierarchy(
    features: list[dict[str, Any]], candidates: list[list[RoleCandidate]], config: ScoringConfig,
) -> dict[str, Any]:
    extract_sequence_evidence(features)
    _qualified(features)
    for f in features:
        f.update(hierarchy_regime_id=None, hierarchy_schema=None, effective_heading_level=None,
                 local_heading_level=None, parent_heading_id=None, local_hierarchy_warning=None)
    initial_regimes = _regimes(features)
    prepare_source_recovery(features, initial_regimes)
    for f in features:
        f["hierarchy_regime_id"] = None
    regimes = _regimes(features)
    by_regime = {r.regime_id: r for r in regimes}
    nodes: list[HeadingNode] = []
    lookup: dict[str, HeadingNode] = {}
    stack: list[HeadingNode] = []
    paths: dict[tuple[str, tuple[int, ...]], HeadingNode] = {}
    family_levels: defaultdict[str, set[int]] = defaultdict(set)
    previous_regime: str | None = None
    regime_stacks: dict[str, list[HeadingNode]] = {}
    virtual_nodes: dict[str, dict[str, Any]] = {}
    feature_by_id = {f["element_id"]: f for f in features}
    for f, roles in zip(features, candidates, strict=True):
        if f["recovery_force_preserve"]:
            for c in roles:
                if c.role.startswith("heading-"):
                    contribute(c, config, "numbering_anchor_conflict", -180,
                               "源编号及原生大纲的多条目冲突，不能确定唯一层级", context=True)
                elif c.role == "unknown":
                    contribute(c, config, "broken_source_sequence", 200, "源序列错误，保留原编号文本", context=True)
            continue
        if f["manual_sequence_candidate"]:
            for c in roles:
                if c.role.startswith("heading-"):
                    contribute(c, config, "manual_sequence_conflict", -180, "连续平行编号无子正文，是列表而非章节", context=True)
                elif c.role == "body-paragraph":
                    contribute(c, config, "manual_sequence_body", 140, "连续编号、同格式和形态、无子内容的局部列表证据", context=True)
            body = next(c for c in roles if c.role == "body-paragraph")
            if f["native_heading_level"] is not None and body.resolved_score < config.medium_score:
                contribute(body, config, "numbering_anchor_conflict", 0,
                           "强手工列表与原生Heading矛盾，body尚不够强时禁止legacy标题回退", context=True)
            continue
        if not f["heading_candidate"]:
            if (f["numbering_family"] or f["native_heading_level"] is not None) \
                    and f["table_context"] is None and not f["list"] and not f["has_complex_object"] \
                    and not f["body_sentence"]:
                for c in roles:
                    if c.role.startswith("heading-"):
                        contribute(c, config, "unconfirmed_heading_structure", -90,
                                   "编号语法尚未得到标题资格，不能仅靠深度升为章节", context=True)
                    elif c.role == "unknown" and not f["author_name_list_shape"]:
                        contribute(c, config, "unconfirmed_numbered_content", 75,
                                   "孤立编号缺少正文归属或标题锚点，保留", context=True)
            continue
        regime = by_regime[f["hierarchy_regime_id"]]
        if previous_regime != regime.regime_id:
            if previous_regime is not None:
                regime_stacks[previous_regime] = list(stack)
            parent = lookup.get(regime.parent_id or "")
            restored = regime_stacks.get(regime.regime_id)
            if restored is not None:
                stack = list(restored)
            elif parent:
                stack = list(stack)
                while stack and stack[-1].element_id != parent.element_id:
                    stack.pop()
                if not stack:
                    stack.append(parent)
            elif regime.parent_id is None:
                stack = []
            previous_regime = regime.regime_id
        parent_node = lookup.get(regime.parent_id or "")
        unsupported_parent = bool(parent_node and parent_node.effective_level is None)
        base = parent_node.effective_level or 0 if parent_node else 0
        family, path = heading_family(f), heading_path(f)
        native = f["native_heading_level"]
        missing_numbered_parent = False
        if not family:
            if f["relative_heading_marker"] or f["hierarchy_reset_marker"]:
                level = (stack[-1].effective_level or 0) + 1 if stack and not f["hierarchy_reset_marker"] else 1
            elif native:
                # Source outline depths identify peers/ancestors. Actual levels
                # still come from the effective parent, never the raw style.
                while stack:
                    top = stack[-1]
                    source_level = top.source_native_level if top.source_native_level is not None else top.effective_level
                    if source_level is None or source_level < native:
                        break
                    stack.pop()
                level = (stack[-1].effective_level or 0) + 1 if stack else 1
            else:
                level = (stack[-1].effective_level or 0) + 1 if stack else 1
        elif regime.schema_name == "decimal_technical":
            level = base + len(path)
            if len(path) > 1 and not f["numbering_suffix_letter"]:
                parent = paths.get((regime.regime_id, path[:-1]))
                missing_numbered_parent = not bool(parent and parent.effective_level
                                                   and any(n.element_id == parent.element_id for n in stack))
        elif family == "DECIMAL":
            parent = paths.get((regime.regime_id, path[:-1]))
            if parent and parent.effective_level and any(n.element_id == parent.element_id for n in stack):
                level = parent.effective_level + 1
            elif native:
                level = native
            else:
                level = base + len(path)
                missing_numbered_parent = True
        else:
            level = base + regime.compressed_levels[family]
        if f["numbering_suffix_letter"] and native:
            level = native
        explicit_recovery_parent = lookup.get(f["recovery_parent_element_id"] or "")
        virtual = None
        hint = f["recovery_virtual_hint"]
        if hint:
            real_parent = lookup.get(hint["parent_id"])
            if real_parent and real_parent.effective_level is not None:
                virtual_level = real_parent.effective_level + hint["level_delta"]
                vid = f"virtual-{regime.regime_id}-{real_parent.element_id}-h{virtual_level}"
                virtual = virtual_nodes.setdefault(vid, {"virtual_node_id": vid, "expected_level": virtual_level,
                    "parent_id": real_parent.element_id, "child_element_ids": [], "regime_id": regime.regime_id,
                    "confidence": hint["confidence"], "reason": "稳定局部子树/实体兄弟模板支持缺失源父层", "evidence_ids": hint["evidence_ids"]})
                if vid not in real_parent.children:
                    real_parent.children.append(vid)
                level = virtual_level + 1
                missing_numbered_parent = False
        elif explicit_recovery_parent and explicit_recovery_parent.effective_level is not None:
            level = explicit_recovery_parent.effective_level + 1
            missing_numbered_parent = False
        while stack and stack[-1].effective_level is not None and stack[-1].effective_level >= level:
            stack.pop()
        if explicit_recovery_parent:
            while stack and stack[-1].element_id != explicit_recovery_parent.element_id:
                stack.pop()
            if not stack:
                stack.append(explicit_recovery_parent)
        parent = stack[-1] if stack else None
        warnings = []
        if missing_numbered_parent:
            warnings.append("missing_numbered_parent")
        if unsupported_parent:
            warnings.append("unsupported_parent")
        if level > 6:
            warnings.append("depth_exceeds_supported_headings")
        parent_level = virtual["expected_level"] if virtual else parent.effective_level if parent else None
        if parent_level is not None and level > parent_level + 1:
            warnings.append("hierarchy_jump")
        effective = level if level <= 6 and not unsupported_parent and not missing_numbered_parent else None
        node = HeadingNode(f["element_id"], f["text"], family or "RELATIVE_HEADING", effective,
                           virtual["virtual_node_id"] if virtual else parent.element_id if parent else None,
                           [], regime.schema_name, regime.regime_id, warnings,
                           source_native_level=native)
        nodes.append(node)
        lookup[node.element_id] = node
        if virtual:
            virtual["child_element_ids"].append(node.element_id)
        elif parent:
            parent.children.append(node.element_id)
        if effective is not None:
            stack.append(node)
            if path:
                paths[(regime.regime_id, path)] = node
        f.update(effective_heading_level=effective, local_heading_level=effective,
                 effective_parent_id=node.parent_id,
                 parent_heading_id=node.parent_id, hierarchy_schema=regime.schema_name,
                 local_hierarchy_warning=", ".join(warnings) if warnings else None)
        if virtual:
            f.update(parent_resolution_type="inferred_virtual_parent", inferred_parent_id=node.parent_id)
        elif parent:
            pf = feature_by_id[parent.element_id]
            f["parent_resolution_type"] = "explicit_numbered_parent" if pf["numbering_family"] else "existing_unnumbered_parent"
            if pf["source_defect_type"] and not f["source_defect_type"]:
                f["source_defect_type"] = pf["source_defect_type"]
                f["hierarchy_confidence"] = pf["hierarchy_confidence"]
            f["hierarchy_evidence"].append({"kind": f["parent_resolution_type"], "element_ids": [parent.element_id],
                                           "detail": "当前局部章节栈及实际前缀父节点"})
        else:
            f["parent_resolution_type"] = "root" if effective == 1 else "unresolved_parent"
        if missing_numbered_parent or "hierarchy_jump" in warnings:
            f["source_defect_type"] = f["source_defect_type"] or "missing_parent_heading"
            f["parent_resolution_type"] = "unresolved_parent"
        if not warnings and not f["hierarchy_confidence"]:
            f["hierarchy_confidence"] = 0.9
        if family and effective:
            family_levels[family].add(effective)
        best_heading_score = max(c.resolved_score for c in roles if c.role.startswith("heading-"))
        if f["relative_heading_marker"] or f["hierarchy_reset_marker"] or f["recovered_heading_family"]:
            best_heading_score += 45
        for c in roles:
            if c.role.startswith("heading-"):
                target_score = best_heading_score + 40 if int(c.role[-1]) == effective else best_heading_score - 35
                contribute(c, config, "effective_heading_level", target_score - c.resolved_score,
                           f"{regime.schema_name}/{regime.regime_id}实际激活层压缩及章节树给出H{effective}", context=True)
                if warnings:
                    contribute(c, config, "hierarchy_jump", -180, "章节树存在真实异常：" + ", ".join(warnings), context=True)
            elif c.role in {"body-paragraph", "document-title", "document-subtitle"}:
                contribute(c, config, "confirmed_heading_structure", -20, "已通过标题资格及章节结构校验", context=True)
            elif c.role == "unknown" and effective is None:
                contribute(c, config, "unsupported_hierarchy", 200, "真实层级超出H1-H6，保留而不钳制", context=True)
    observed_levels: defaultdict[tuple[str, str], set[int]] = defaultdict(set)
    for node in nodes:
        if node.effective_level is None:
            continue
        r = by_regime[node.regime]
        f = feature_by_id[node.element_id]
        key = f"DECIMAL-{len(heading_path(f))}" if r.schema_name == "decimal_technical" and heading_path(f) else node.family
        if key in r.compressed_levels:
            observed_levels[r.regime_id, key].add(node.effective_level)
    for regime in regimes:
        parent_node = lookup.get(regime.parent_id or "")
        regime.base_level = parent_node.effective_level if parent_node else 0
        regime.effective_level_variants = {family: sorted(observed_levels[regime.regime_id, family]) for family in regime.compressed_levels}
        regime.effective_levels = {family: levels[0] if len(levels) == 1 else None
                                   for family, levels in regime.effective_level_variants.items()}
    return {
        "hierarchy_schemas": [asdict(s) for s in SCHEMAS],
        "hierarchy_regimes": [asdict(r) for r in regimes],
        "heading_tree": [asdict(n) for n in nodes],
        "virtual_heading_nodes": list(virtual_nodes.values()),
        "hierarchy_warnings": [{"element_id": n.element_id, "warnings": n.warnings} for n in nodes if n.warnings],
        "effective_numbering_family_levels": {family: next(iter(levels)) for family, levels in family_levels.items() if len(levels) == 1},
    }
