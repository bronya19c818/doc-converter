"""Evidence-bound recovery of defective source structure, without Word edits.

Source numbering/outline facts remain immutable. The hints below are separate
structural hypotheses; neither source IDs nor external ground truth are rules.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from doc_converter.docx_direct.manual_sequences import structure_safe


def heading_family(f: dict[str, Any]) -> str | None:
    return f.get("recovered_heading_family") or f["numbering_family"]


def heading_path(f: dict[str, Any]) -> tuple[int, ...]:
    return tuple(f.get("recovered_numbering_path") or f["numbering_path"])


def heading_outline(f: dict[str, Any]) -> int | None:
    return f.get("recovered_outline_level") or f["native_heading_level"]


def _evidence(f: dict[str, Any], kind: str, ids: list[str], detail: str) -> None:
    f["hierarchy_evidence"].append({"kind": kind, "element_ids": ids, "detail": detail})


def _plain_heading(f: dict[str, Any]) -> bool:
    return structure_safe(f) and not f["numbering_family"] and not f["body_sentence"] \
        and f["text_length"] <= 24 and not f["manual_sequence_candidate"]


def prepare_source_recovery(features: list[dict[str, Any]], regimes: list[Any]) -> None:
    """Two local evidence passes: prefer real entities, then missing entities."""
    by_regime = {r.regime_id: r for r in regimes}
    following: list[int | None] = [None] * len(features)
    next_index = None
    for i in range(len(features) - 1, -1, -1):
        following[i] = next_index
        if features[i]["text_length"] or features[i]["has_complex_object"] or features[i]["table_context"] is not None \
                or features[i]["has_section_break"] or features[i]["hierarchy_reset_marker"]:
            next_index = i
    for f in features:
        f.update(source_defect_type=None, source_defect_resolution=None,
                 parent_resolution_type="unresolved_parent", inferred_parent_id=None,
                 effective_parent_id=None, source_native_heading_level=f["native_heading_level"],
                 hierarchy_confidence=0.0, hierarchy_evidence=[], recovered_heading_family=None,
                 recovered_numbering_path=[], recovered_outline_level=None,
                 recovery_parent_element_id=None, recovery_virtual_hint=None, recovery_force_preserve=False)

    blocks: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    root = None
    members: list[dict[str, Any]] = []
    pending_reset = False
    for f in features:
        boundary = pending_reset or f["hierarchy_reset_marker"] or f["reference_boundary"]
        pending_reset = f["has_section_break"]
        r = by_regime.get(f["hierarchy_regime_id"])
        major = f["heading_candidate"] and (
            f["native_heading_level"] == 1 or f["numbering_family"] in {"CHAPTER", "SECTION", "CN_ENUM"}
            and f["native_heading_level"] is None and (r is None or r.parent_native_level is None)
        )
        if boundary or major:
            if root:
                blocks.append((root, members))
            root, members = (f, []) if major else (None, [])
        elif root:
            members.append(f)
    if root:
        blocks.append((root, members))

    profiles: set[tuple[int, str | None, str | None, str | None]] = set()
    summaries = []
    positions = {f["element_id"]: i for i, f in enumerate(features)}
    for root, members in blocks:
        if root["numbering_family"] not in {"CHAPTER", "SECTION", "CN_ENUM"}:
            continue
        direct = []
        for f in members:
            r = by_regime.get(f["hierarchy_regime_id"])
            if f["heading_candidate"] and (r is None or r.parent_id in {None, root["element_id"]}):
                direct.append(f)
        arms = [f for f in direct if f["numbering_family"] == "ARABIC_ENUM"]
        brackets = [f for f in direct if f["numbering_family"] == "CN_BRACKET"]
        sibling = next((f for f in brackets if f["numbering_ordinal"] == 2), None)
        before_sibling = [f for f in arms if not sibling or positions[f["element_id"]] < positions[sibling["element_id"]]]
        decimal_groups: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
        for f in members:
            p = f["numbering_path"]
            if f["numbering_family"] == "DECIMAL" and len(p) >= 2 and structure_safe(f) \
                    and (not sibling or positions[f["element_id"]] < positions[sibling["element_id"]]):
                decimal_groups[p[0]].append(f)
        real_parent = None
        if sibling and len(before_sibling) >= 2:
            before_ids = {p["element_id"] for p in before_sibling}
            for f in members:
                if not _plain_heading(f) or f["native_heading_level"] is not None:
                    continue
                if positions[f["element_id"]] >= positions[sibling["element_id"]]:
                    continue
                if positions[f["element_id"]] >= positions[before_sibling[0]["element_id"]]:
                    continue
                j = following[positions[f["element_id"]]]
                child = features[j] if j is not None else None
                first_numbered = bool(child and child["element_id"] in before_ids and child["numbering_ordinal"] == 1)
                grandchild_index = following[j] if j is not None else None
                grandchild = features[grandchild_index] if grandchild_index is not None else None
                first_unnumbered = bool(child and _plain_heading(child) and child["native_heading_level"] is None
                                        and grandchild and grandchild["numbering_family"] == "DECIMAL"
                                        and grandchild["numbering_path"][0] == 1 and len(decimal_groups[1]) >= 2)
                if first_numbered or first_unnumbered:
                    real_parent = f
                    f.update(heading_candidate=True, recovered_heading_family="CN_BRACKET",
                             recovery_parent_element_id=root["element_id"],
                             source_defect_type="missing_numbering_on_existing_heading", hierarchy_confidence=0.95)
                    _evidence(f, "existing_entity_and_parallel_children", [root["element_id"], *[p["element_id"] for p in before_sibling], sibling["element_id"]],
                              "真实未编号短标题后有多个挂正文的数字主题，后续中文括号第二节提供同父层证据")
                    if first_unnumbered:
                        assert child is not None
                        _evidence(f, "unnumbered_first_child_with_numeric_body", [child["element_id"], *[p["element_id"] for p in decimal_groups[1]]],
                                  "首个真实子主题也未编号，但其后多个1.x正文条款和其他同父主题提供独立前缀证据")
                    break
        if real_parent:
            assert sibling is not None
            for f in before_sibling:
                f["recovery_parent_element_id"] = real_parent["element_id"]
            start, end = positions[real_parent["element_id"]], positions[sibling["element_id"]]
            existing_roots = {p["numbering_path"][0] for p in before_sibling}
            for f in members:
                if not _plain_heading(f) or f is real_parent or f["native_heading_level"] is not None:
                    continue
                i = positions[f["element_id"]]
                j = following[i]
                child = features[j] if j is not None else None
                if not (start < i < end and child and child["numbering_family"] == "DECIMAL"):
                    continue
                ordinal = child["numbering_path"][0]
                peers = decimal_groups[ordinal]
                if len(peers) < 2 or ordinal in existing_roots:
                    continue
                f.update(heading_candidate=True, recovered_heading_family="ARABIC_ENUM",
                         recovered_numbering_path=[ordinal], recovery_parent_element_id=real_parent["element_id"],
                         source_defect_type="missing_numbering_on_existing_heading", hierarchy_confidence=0.92)
                _evidence(f, "real_entity_with_consistent_child_prefix", [real_parent["element_id"], *[p["element_id"] for p in peers]],
                          "真实短主题后多个数字条款共享根前缀，与同父数字主题系列并列；前缀只作内部索引，不写入文本")
        scope = root["heading_qualification_scope"]
        style = before_sibling[0]["original_style_id"] if before_sibling else None
        key = (scope, root["hierarchy_regime_id"], root["numbering_family"], style)
        explicit_first = any(f["numbering_ordinal"] == 1 for f in brackets)
        if (real_parent or explicit_first) and len(before_sibling) >= 2:
            profiles.add(key)
        # Source-native 3/4 pairs corroborate a source layer, not merely a
        # single bad outline value. A matching explicit sibling template can
        # also corroborate a one-parent subtree with multiple child headings.
        native_roots = [f for f in arms if f["native_heading_level"] == 3]
        native_children = []
        source_owner = None
        for f in members:
            if not f["heading_candidate"]:
                continue
            if f["numbering_family"] == "ARABIC_ENUM":
                r = by_regime.get(f["hierarchy_regime_id"])
                if f["native_heading_level"] == 3:
                    source_owner = f
                elif f["native_heading_level"] is not None and f["native_heading_level"] < 3 \
                        or f["native_heading_level"] is None and (r is None or r.parent_id in {None, root["element_id"]}):
                    source_owner = None
            elif f["numbering_family"] == "CN_BRACKET" and f["native_heading_level"] == 2:
                source_owner = None
            elif source_owner and f["numbering_family"] == "DECIMAL" and f["native_heading_level"] == 4 \
                    and len(f["numbering_path"]) == 2 and f["numbering_path"][0] == source_owner["numbering_ordinal"]:
                native_children.append(f)
        all_native_pairs = any(f["numbering_family"] == "CN_BRACKET" and f["native_heading_level"] == 2 for f in members) \
            and any(f["numbering_family"] == "ARABIC_ENUM" and f["native_heading_level"] == 3 for f in members) and bool(native_children)
        if sibling:
            native_roots = [f for f in native_roots if positions[f["element_id"]] < positions[sibling["element_id"]]]
            native_children = [f for f in native_children if positions[f["element_id"]] < positions[sibling["element_id"]]]
        direct_ordinals = {f["numbering_ordinal"] for f in native_roots}
        owner_counts = Counter(f["numbering_path"][0] for f in native_children if f["numbering_path"][0] in direct_ordinals)
        if all_native_pairs:
            profiles.add((scope, root["hierarchy_regime_id"], root["numbering_family"], "native-3-4"))
        summaries.append((root, arms, sibling, real_parent, explicit_first, key, native_roots, native_children, owner_counts))

        _correct_peer_outlines(members, by_regime)

    for root, arms, sibling, real_parent, explicit_first, key, native_roots, native_children, owner_counts in summaries:
        if real_parent or explicit_first:
            continue
        repeated = sibling is not None and len(arms) >= 2 and key in profiles
        stable_native = len(native_roots) >= 2 and (
            len(owner_counts) >= 2 or max(owner_counts.values(), default=0) >= 2
            and (root["heading_qualification_scope"], root["hierarchy_regime_id"], root["numbering_family"], "native-3-4") in profiles
        )
        targets = native_roots if stable_native else arms if repeated else []
        # An explicit first bracket parent in this block already supplies the
        # missing layer. Targets inside its own regime are not direct arms.
        if not targets:
            continue
        evidence = [root["element_id"], *[f["element_id"] for f in targets], *[f["element_id"] for f in native_children]]
        if sibling:
            evidence.append(sibling["element_id"])
        for f in targets:
            if sibling and positions[f["element_id"]] >= positions[sibling["element_id"]]:
                continue
            f.update(source_defect_type="missing_parent_heading", hierarchy_confidence=0.92,
                     recovery_virtual_hint={"parent_id": root["element_id"], "level_delta": 1,
                                            "confidence": 0.92, "evidence_ids": evidence})
            _evidence(f, "corroborated_missing_source_layer", evidence,
                      "相同边界内的实体/编号兄弟模板或多个稳定原生3/4子树，支持缺失源父层；不是未使用的schema层")

    _preserve_broken_sequences(features, regimes, positions)


def _correct_peer_outlines(members: list[dict[str, Any]], by_regime: dict[str, Any]) -> None:
    parent = None
    peer_group: list[dict[str, Any]] = []

    def correct_peer_group() -> None:
        if parent is None:
            return
        expected = parent["native_heading_level"] + 1
        reliable = [p for p in peer_group if p["native_heading_level"] == expected]
        if len(reliable) < 2:
            return
        previous_ordinal = None
        for p in peer_group:
            if p["native_heading_level"] is not None and p["native_heading_level"] != expected \
                    and previous_ordinal is not None and p["numbering_ordinal"] == previous_ordinal + 1:
                p.update(recovered_outline_level=expected, recovery_parent_element_id=parent["element_id"],
                         source_defect_type="incorrect_source_outline", hierarchy_confidence=0.94)
                _evidence(p, "numbered_peers_beneath_explicit_parent", [parent["element_id"], *[q["element_id"] for q in reliable]],
                          "明确括号父主题与至少两个稳定同级编号标题一致，连续编号条目的源Heading偏离同级")
            previous_ordinal = p["numbering_ordinal"]

    for f in members:
        if f["heading_candidate"] and f["numbering_family"] == "CN_BRACKET" and f["native_heading_level"] == 2:
            correct_peer_group()
            parent, peer_group = f, []
        elif parent and f["heading_candidate"] and f["numbering_family"] == "ARABIC_ENUM":
            r = by_regime.get(f["hierarchy_regime_id"])
            if r is None or r.parent_native_level is None or r.parent_native_level < parent["native_heading_level"] + 1:
                peer_group.append(f)
    correct_peer_group()


def _preserve_broken_sequences(
    features: list[dict[str, Any]], regimes: list[Any], positions: dict[str, int],
) -> None:
    # Detect a run of deeper source outlines that collides with the next
    # outer numbered peer. Unlike a single bad Heading, the sequence itself
    # is contradictory; preserve it instead of declaring one level true.
    next_candidate: list[int | None] = [None] * len(features)
    candidate_index = None
    for i in range(len(features) - 1, -1, -1):
        next_candidate[i] = candidate_index
        if features[i]["heading_candidate"]:
            candidate_index = i
    for r in regimes:
        peers = [features[i] for i in r.indices if features[i]["numbering_family"] == "ARABIC_ENUM"
                 and features[i]["native_heading_level"] is not None]
        if len(peers) < 4:
            continue
        counts = Counter(f["native_heading_level"] for f in peers)
        usual = max(counts, key=lambda n: counts[n])
        tail = []
        for f in reversed(peers):
            if f["native_heading_level"] <= usual:
                break
            tail.append(f)
        tail.reverse()
        if len(tail) < 2 or not all(b["numbering_ordinal"] == a["numbering_ordinal"] + 1 for a, b in zip(tail, tail[1:])):
            continue
        last = positions[tail[-1]["element_id"]]
        closing_index = next_candidate[last]
        closing = features[closing_index] if closing_index is not None else None
        if not (closing and closing["numbering_family"] == "ARABIC_ENUM"
                and closing["numbering_ordinal"] == tail[-1]["numbering_ordinal"]
                and closing["native_heading_level"] is not None and closing["native_heading_level"] < usual):
            continue
        for f in tail:
            f.update(source_defect_type="broken_numbering_sequence", recovery_force_preserve=True,
                     hierarchy_confidence=0.95, heading_candidate=False)
            _evidence(f, "conflicting_numbered_scope_closure", [p["element_id"] for p in peers] + [closing["element_id"]],
                      "多个连续条目原生深度偏离同父系列，随后同编号更浅主节重复关闭；不能把错误编号当唯一层级真值")


def finish_source_audit(elements: list[Any], baselines: dict[str, Any]) -> None:
    """Report actual selected outcomes, without selecting or modifying Word."""
    by_id = {e.element_id: e for e in elements}
    counts: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    for e in elements:
        f = e.features
        if not f.get("source_defect_type"):
            continue
        d = e.selected_decision
        if d.action == "mapped" and d.role == f"heading-{f['effective_heading_level']}":
            state = "resolved"
        elif d.action == "preserved" and f["recovery_force_preserve"]:
            state = "resolved_conservatively"
        else:
            state = "unresolved"
        f["source_defect_resolution"] = state
        counts[f["source_defect_type"]] += 1
        outcomes[state] += 1
    for node in baselines["heading_tree"]:
        f = by_id[node["element_id"]].features
        node.update(source_defect_type=f["source_defect_type"], parent_resolution_type=f["parent_resolution_type"],
                    source_defect_resolution=f["source_defect_resolution"], hierarchy_confidence=f["hierarchy_confidence"],
                    hierarchy_evidence=f["hierarchy_evidence"])
    baselines["source_structure_summary"] = {"defect_counts": dict(counts), "resolution_counts": dict(outcomes),
        "existing_parent_recoveries": sum(f.features.get("recovered_heading_family") is not None for f in elements),
        "virtual_parent_count": len(baselines["virtual_heading_nodes"])}
