"""Local sequence facts, independent of roles and wording-specific dictionaries."""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

CHINESE_ORDER = ("PART", "CHAPTER", "SECTION", "CN_ENUM", "CN_BRACKET", "ARABIC_ENUM", "ARABIC_BRACKET", "CIRCLED")


def structure_safe(f: dict[str, Any]) -> bool:
    return bool(f["text_length"] and f["table_context"] is None and not f["list"] and not any(
        f[k] for k in ("has_complex_object", "has_manual_break", "explicit_author_label",
                       "explicit_organization_label", "explicit_date",
                       "person_name_pattern", "organization_pattern", "caption_pattern", "reference_boundary")
    ) and not f["native_title_style"]
        and f.get("semantic_preface_role") not in {"document-title", "document-subtitle"}
        and not (f["author_name_list_shape"] and not f["numbering_family"]))


def _child_content(f: dict[str, Any], n: dict[str, Any] | None) -> bool:
    family, path = f["numbering_family"], f["numbering_path"]
    if n is None or n["has_section_break"] or n["hierarchy_reset_marker"]:
        return False
    if n["table_context"] is not None or n["has_complex_object"]:
        return True
    other, other_path = n["numbering_family"], n["numbering_path"]
    if family == other:
        return bool(family == "DECIMAL" and len(other_path) > len(path) and other_path[:len(path)] == path)
    if family == "ARABIC_ENUM" and other == "DECIMAL" and path and other_path[:1] == path:
        return True
    if other in CHINESE_ORDER and family in CHINESE_ORDER:
        return CHINESE_ORDER.index(other) > CHINESE_ORDER.index(family)
    if n["native_heading_level"]:
        return n["native_heading_level"] > (f["native_heading_level"] or 1)
    return True


def extract_sequence_evidence(features: list[dict[str, Any]]) -> None:
    next_content: list[dict[str, Any] | None] = [None] * len(features)
    following = None
    for i in range(len(features) - 1, -1, -1):
        next_content[i] = following
        f = features[i]
        if f["text_length"] or f["has_complex_object"] or f["table_context"] is not None \
                or f["has_section_break"] or f["hierarchy_reset_marker"]:
            following = f
    for i, f in enumerate(features):
        f.update(manual_sequence_candidate=False, manual_sequence_family=None,
                 manual_sequence_uncertain=False,
                 manual_sequence_length=0, manual_sequence_index=None,
                 manual_sequence_same_style_ratio=0.0, manual_sequence_same_format_ratio=0.0,
                 manual_sequence_parallel_shape=False, manual_sequence_has_child_content=False,
                 has_child_content_before_next_peer=_child_content(f, next_content[i]) if f["numbering_family"] else False,
                 next_peer_distance=None)
    eligible = [
        structure_safe(f) and f["numbering_family"] not in {None, "CHAPTER", "SECTION"}
        and f["numbering_ordinal"] is not None
        for f in features
    ]
    i = 0
    while i < len(features):
        if not eligible[i]:
            i += 1
            continue
        group = [i]
        end = i + 1
        while end < len(features) and eligible[end]:
            previous, current = features[group[-1]], features[end]
            if current["numbering_family"] != previous["numbering_family"] \
                    or current["numbering_ordinal"] != previous["numbering_ordinal"] + 1 \
                    or current["numbering_family"] == "DECIMAL" \
                    and current["numbering_path"][:-1] != previous["numbering_path"][:-1]:
                break
            group.append(end)
            end += 1
        # A closing outer heading can continue the ordinal but owns body content.
        entries = [j for j in group if not features[j]["has_child_content_before_next_peer"]]
        if len(entries) >= 3:
            styles = Counter(features[j]["original_style_id"] for j in entries)
            formats = Counter(json.dumps({k: features[j][k] for k in (
                "alignment", "dominant_font_size_pt", "dominant_bold", "indentation",
            )}, sort_keys=True) for j in entries)
            style_ratio = max(styles.values()) / len(entries)
            format_ratio = max(formats.values()) / len(entries)
            lengths = [features[j]["text_length"] for j in entries]
            parallel = max(lengths) <= 4 * max(1, min(lengths))
            native = any(features[j]["native_heading_level"] is not None for j in entries)
            quoted = all(features[j]["fully_quoted_content"] for j in entries)
            if style_ratio >= 0.8 and format_ratio >= 0.8 and parallel and (not native or quoted):
                for position, j in enumerate(entries, 1):
                    features[j].update(
                        manual_sequence_candidate=True,
                        manual_sequence_family=features[j]["numbering_family"],
                        manual_sequence_length=len(entries), manual_sequence_index=position,
                        manual_sequence_same_style_ratio=style_ratio,
                        manual_sequence_same_format_ratio=format_ratio,
                        manual_sequence_parallel_shape=parallel, next_peer_distance=1,
                    )
                first = entries[0]
                if first > 0:
                    parent = features[first - 1]
                    child = features[first]
                    if parent["numbering_family"] == child["numbering_family"] \
                            and parent["numbering_ordinal"] and child["numbering_ordinal"] < parent["numbering_ordinal"]:
                        parent["has_child_content_before_next_peer"] = True
        elif len(group) >= 2 and not any(features[j]["native_heading_level"] is not None for j in group):
            # A body paragraph only after the final item does not prove that
            # adjacent bare ordinals are independent headings.
            for j in group:
                features[j]["manual_sequence_uncertain"] = True
        i = max(i + 1, end)

