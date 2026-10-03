"""Full-document context corrections for shadow candidates only."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from doc_converter.docx_direct.model import RoleCandidate
from doc_converter.docx_direct.scoring import ScoringConfig, contribute


def _safe_heading(f: dict[str, Any]) -> bool:
    return bool(
        f["short_text"] and not f["body_sentence"] and f["table_context"] is None
        and not f["list"]
        and not any(f[k] for k in ("has_field", "has_drawing", "has_manual_break",
                                  "explicit_author_label", "explicit_organization_label",
                                  "explicit_date", "caption_pattern", "reference_boundary"))
        and (f["native_heading_level"] or f["numbering_family"]
             or isinstance(f["outline_level"], int) and 0 <= f["outline_level"] <= 5)
    )


def _assign_shadow_regions(features: list[dict[str, Any]], config: ScoringConfig) -> None:
    body_started = False
    postface_started = False
    for f in features:
        outside = f["table_context"] is None and not f["list"]
        if outside and f["reference_boundary"] and not any(
            f[k] for k in ("has_field", "has_drawing", "has_manual_break")
        ):
            postface_started = True
        sentence_boundary = f["body_sentence"] and not any(
            f[k] for k in ("explicit_author_label", "explicit_organization_label", "explicit_date", "caption_pattern")
        )
        ratio = f["font_size_to_body_ratio"]
        leading_large = (
            f["document_order"] < 12 and f["short_text"] and not f["has_terminal_punctuation"]
            and ratio is not None and ratio >= config.larger_font_ratio
        )
        plain_boundary = f["text_length"] and f["alignment"] != "center" and not f["native_title_style"] and not leading_large and not any(
            f[k] for k in ("explicit_author_label", "explicit_organization_label", "explicit_date",
                          "person_name_pattern", "organization_pattern", "caption_pattern",
                          "reference_boundary", "has_field", "has_drawing", "has_manual_break")
        )
        if outside and (_safe_heading(f) or sentence_boundary or plain_boundary):
            body_started = True
        region = "postface" if postface_started else "body" if body_started else "preface"
        f.update(region=region, is_preface=region == "preface",
                 is_body=region == "body", is_postface=region == "postface")


def _numbering_levels(
    features: list[dict[str, Any]],
) -> tuple[dict[str, int], set[str], set[str]]:
    """Infer family ordering from safe occurrences, with native/outline anchors."""

    anchors: defaultdict[str, set[int]] = defaultdict(set)
    families: list[str] = []
    has_decimal = any(_safe_heading(f) and f["numbering_family"] == "DECIMAL" for f in features)
    for f in features:
        family = f["numbering_family"]
        if not family or family == "DECIMAL" or not _safe_heading(f):
            continue
        if family not in families:
            families.append(family)
        anchor = f["native_heading_level"]
        if anchor is None and not f["based_on_heading"] and isinstance(f["outline_level"], int):
            anchor = f["outline_level"] + 1
        if anchor and 1 <= anchor <= 6:
            anchors[family].add(anchor)
    conflicts = {family for family, levels in anchors.items() if len(levels) > 1}
    mapping: dict[str, int] = {}
    previous = 0
    for family in families:
        if family in conflicts:
            continue
        if anchors[family]:
            level = next(iter(anchors[family]))
        elif family == "ARABIC_ENUM" and has_decimal and not any(
            c in families for c in ("CN_ENUM", "CN_BRACKET", "CHAPTER")
        ):
            level = 1
        else:
            level = previous + 1
        # Unsupported depth remains unresolved rather than clamped to six.
        if level <= 6:
            mapping[family] = level
        previous = level
    # Repeated single-family ordinals could equally be a manual operation list.
    # Strong context requires a native anchor, a nested family system, or decimals.
    corroborated = {
        family for family in mapping
        if anchors[family] or len(families) > 1 or has_decimal
    }
    return mapping, conflicts, corroborated


def resolve_candidates(
    features: list[dict[str, Any]], candidates: list[list[RoleCandidate]], config: ScoringConfig,
) -> dict[str, Any]:
    """Correct candidates with additive context evidence; leave raw scores intact."""

    _assign_shadow_regions(features, config)
    numbering, conflicts, corroborated = _numbering_levels(features)
    for f, roles in zip(features, candidates, strict=True):
        for c in roles:

            def add(key: str, points: float, reason: str) -> None:
                contribute(c, config, key, points, reason, context=True)

            if c.role in {"document-title", "document-subtitle", "author", "organization-department", "date"}:
                add("preface_context" if f["is_preface"] else "outside_preface",
                    20 if f["is_preface"] else -70, f"全文区域为 {f['region']}")
            if c.role == "body-paragraph":
                add("body_region" if f["is_body"] else "outside_body",
                    10 if f["is_body"] else -15, f"全文区域为 {f['region']}")
            if c.role == "reference-entry":
                add("reference_region" if f["is_postface"] else "outside_reference_region",
                    60 if f["is_postface"] and f["table_context"] is None else -60,
                    "参考文献边界后的区域证据")
            if c.role.startswith("heading-"):
                level = int(c.role[-1])
                if f["is_body"]:
                    add("heading_body_region", 5, "位于正文结构区域")
                family = f["numbering_family"]
                if family in conflicts:
                    add("numbering_anchor_conflict", -30, "同一编号家族出现不一致的原生/大纲层级锚点")
                elif family in numbering and _safe_heading(f):
                    expected = numbering[family]
                    if level == expected and family not in corroborated:
                        add("numbering_family_uncorroborated", 10,
                            f"全文仅有未获层级锚点的 {family} 家族；第 {expected} 级只是弱推断，可能是手工列表")
                    else:
                        add("numbering_family_match" if level == expected else "numbering_family_other",
                            40 if level == expected else -35,
                            f"全文编号家族 {family} 按出现顺序和层级锚点推断为第 {expected} 级")

    # Rank title candidates after region corrections. Only a clear contender can
    # provide title/subtitle ordering evidence; metadata and table text are excluded.
    titles = [
        (i, next(c for c in roles if c.role == "document-title"))
        for i, (f, roles) in enumerate(zip(features, candidates, strict=True))
        if f["is_preface"] and f["table_context"] is None and f["short_text"]
        and (f["alignment"] == "center" or f["native_title_style"] == "title"
             or f["font_size_to_body_ratio"] is not None
             and f["font_size_to_body_ratio"] >= config.larger_font_ratio)
        and not f["body_sentence"] and not any(f[k] for k in (
            "explicit_author_label", "explicit_organization_label", "explicit_date",
            "person_name_pattern", "organization_pattern", "caption_pattern"))
    ]
    title_index: int | None = None
    if titles:
        title_index, title = max(titles, key=lambda pair: (pair[1].resolved_score, -pair[0]))
        if title.resolved_score < config.medium_score:
            title_index = None
    if title_index is not None:
        title_size = features[title_index]["dominant_font_size_pt"]
        subtitle_index: int | None = None
        for i, f in enumerate(features):
            size = f["dominant_font_size_pt"]
            if i <= title_index or not f["is_preface"] or f["table_context"] is not None:
                continue
            if any(f[k] for k in ("explicit_author_label", "explicit_organization_label", "explicit_date", "person_name_pattern", "organization_pattern")):
                break
            if f["alignment"] != "center" or not f["short_text"] or f["body_sentence"]:
                continue
            if f["caption_pattern"]:
                continue
            if title_size and size and size < title_size:
                subtitle_index = i
                break
        for i, roles in enumerate(candidates):
            for c in roles:
                if c.role == "document-title":
                    contribute(c, config, "primary_title" if i == title_index else "other_title_candidate",
                               15 if i == title_index else -25,
                               "文前主标题候选竞争结果", context=True)
                if c.role == "document-subtitle":
                    contribute(c, config, "subtitle_after_title" if i == subtitle_index else "no_subtitle_order",
                               30 if i == subtitle_index else -25,
                               "副标题须在主标题之后、元数据之前，且字号更小", context=True)
                if c.role in {"author", "organization-department", "date"} and i < title_index:
                    contribute(c, config, "metadata_before_title", -10,
                               "元数据位于主标题之前，文前顺序证据较弱", context=True)

    previous_heading = 0
    for f, roles in zip(features, candidates, strict=True):
        if not _safe_heading(f) or not f["is_body"]:
            continue
        top = max(roles, key=lambda c: c.resolved_score)
        if not top.role.startswith("heading-") or top.resolved_score < config.medium_score:
            continue
        level = int(top.role[-1])
        if previous_heading and level > previous_heading + 1:
            contribute(top, config, "hierarchy_jump", -30,
                       f"前一个标题为 {previous_heading} 级，本段直接跳到 {level} 级；降低置信并禁止映射",
                       context=True)
        previous_heading = level
    return {
        "numbering_family_levels": numbering,
        "numbering_conflicts": sorted(conflicts),
        "numbering_corroborated_families": sorted(corroborated),
        "primary_title_element_index": title_index,
    }
