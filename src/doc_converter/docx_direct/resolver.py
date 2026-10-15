"""Full-document context corrections for shadow candidates only."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from doc_converter.docx_direct.hierarchy_resolver import resolve_hierarchy
from doc_converter.docx_direct.manual_sequences import extract_sequence_evidence
from doc_converter.docx_direct.model import RoleCandidate
from doc_converter.docx_direct.scoring import ScoringConfig, contribute


def _safe_heading(f: dict[str, Any]) -> bool:
    return bool(
        f.get("semantic_preface_role") not in {"document-title", "document-subtitle"}
        and
        f["short_text"] and not f["body_sentence"] and f["table_context"] is None
        and not f["list"]
        and not f.get("manual_sequence_candidate", False)
        and not (f["author_name_list_shape"] and not f["numbering_family"])
        and not any(f[k] for k in ("has_complex_object", "has_manual_break",
                                  "explicit_author_label", "explicit_organization_label",
                                  "explicit_date", "caption_pattern", "reference_boundary"))
        and (f["native_heading_level"] or f["numbering_family"]
             or isinstance(f["outline_level"], int) and 0 <= f["outline_level"] <= 5)
    )


def _assign_shadow_regions(features: list[dict[str, Any]], config: ScoringConfig) -> None:
    body_started = False
    postface_started = False
    for index, f in enumerate(features):
        f["body_started_before"] = body_started
        outside = f["table_context"] is None and not f["list"]
        author_affiliation = (
            not body_started and index > 0 and features[index - 1]["author_name_list_shape"]
            and f["author_affiliation_pattern"] and not f["has_complex_object"]
        )
        if outside and f["reference_boundary"] and not any(
            f[k] for k in ("has_complex_object", "has_manual_break")
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
        plain_boundary = f["text_length"] and f["alignment"] != "center" and not f["native_title_style"] and not leading_large and not author_affiliation and not any(
            f[k] for k in ("explicit_author_label", "explicit_organization_label", "explicit_date",
                          "person_name_pattern", "author_name_list_shape", "organization_pattern", "caption_pattern",
                          "reference_boundary", "has_complex_object", "has_manual_break")
        )
        if outside and f.get("semantic_preface_role") not in {"document-title", "document-subtitle"} and (_safe_heading(f) or sentence_boundary or plain_boundary):
            body_started = True
        region = "postface" if postface_started else "body" if body_started else "preface"
        f.update(region=region, is_preface=region == "preface",
                 is_body=region == "body", is_postface=region == "postface")


def _author_followup(features: list[dict[str, Any]], index: int) -> bool:
    """Confirm adjacent metadata, never borrow a date from beyond a body boundary."""
    for f in features[index + 1:index + 4]:
        if f["table_context"] is not None or f["list"] or any(f[k] for k in (
            "has_complex_object", "has_manual_break", "reference_boundary", "caption_pattern",
        )):
            return False
        # The abstract may itself start body; no earlier body paragraph may intervene.
        if not f["is_preface"] and not (f["abstract_label"] and not f["body_started_before"]):
            return False
        if any(f[k] for k in ("explicit_organization_label", "organization_pattern",
                              "author_affiliation_pattern", "explicit_date", "abstract_label")) \
                or f["native_title_style"] == "subtitle" and f["short_text"] and not f["body_sentence"]:
            return True
        if _safe_heading(f) or f["body_sentence"]:
            return False
    return False


def _global_numbering_prior(
    features: list[dict[str, Any]],
) -> tuple[dict[str, int], set[str], set[str]]:
    """Compatibility audit prior; it does not assign effective heading levels."""

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

    extract_sequence_evidence(features)
    _assign_shadow_regions(features, config)
    numbering, conflicts, corroborated = _global_numbering_prior(features)
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
                if f["is_body"]:
                    add("heading_body_region", 5, "位于正文结构区域")

    # Rank title candidates after region corrections. Only a clear contender can
    # provide title/subtitle ordering evidence; metadata and table text are excluded.
    titles = [
        (i, next(c for c in roles if c.role == "document-title"))
        for i, (f, roles) in enumerate(zip(features, candidates, strict=True))
        if f["is_preface"] and f["table_context"] is None and f["short_text"]
        and (f.get("semantic_preface_role") == "document-title" or f["alignment"] == "center" or f["native_title_style"] == "title"
             or f["font_size_to_body_ratio"] is not None
             and f["font_size_to_body_ratio"] >= config.larger_font_ratio)
        and not f["body_sentence"] and not any(f[k] for k in (
            "explicit_author_label", "explicit_organization_label", "explicit_date",
            "person_name_pattern", "author_name_list_shape", "organization_pattern", "caption_pattern",
            "has_complex_object", "has_manual_break"))
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
            if any(f[k] for k in ("explicit_author_label", "explicit_organization_label", "explicit_date", "person_name_pattern", "author_name_list_shape", "organization_pattern")):
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

        for i, (f, roles) in enumerate(zip(features, candidates, strict=True)):
            author_context = (
                title_index < i <= title_index + 4 and f["is_preface"]
                and f["author_name_list_shape"] and f["author_surname_match_count"] > 0
                and not f["numbering_family"]
                and f["table_context"] is None and not f["list"]
                and not f["has_complex_object"] and not f["has_manual_break"]
                and _author_followup(features, i)
            )
            if not author_context:
                continue
            for c in roles:
                if c.role == "author":
                    contribute(c, config, "author_list_after_title", 65 if f["author_surname_match_ratio"] == 1 else 30,
                               "姓名列表紧跟题名且后续单位、日期或摘要相互印证", context=True)
                elif c.role.startswith("heading-"):
                    contribute(c, config, "preface_author_conflict", -120,
                               "文前作者语义与脏原生 Heading 样式冲突", context=True)
                elif c.role == "unknown":
                    contribute(c, config, "author_list_context_confirmed", -150,
                               "文前顺序已印证作者列表，撤销缺上下文的保留倾向", context=True)

    for i, (f, roles) in enumerate(zip(features, candidates, strict=True)):
        neighbors = features[max(0, i - 1):i] + features[i + 1:i + 2]
        ordinary_phrase = (
            f["is_body"] and f["short_text"] and f["common_body_style"]
            and f["table_context"] is None and not f["list"]
            and not any(f[k] for k in (
                "native_heading_level", "numbering_family", "caption_pattern",
                "reference_boundary", "organization_pattern", "explicit_author_label",
                "explicit_organization_label", "explicit_date", "has_complex_object", "author_name_list_shape",
                "has_manual_break",
            ))
            and len(neighbors) == 2 and all(
                n["is_body"] and n["body_sentence"] and n["table_context"] is None
                and not n["list"] for n in neighbors
            )
        )
        organization_cluster = (
            title_index is not None and title_index < i <= title_index + 4
            and f["is_preface"] and f["organization_pattern"]
            and f["table_context"] is None and not f["list"]
            and any(n["is_preface"] and n["explicit_date"] for n in features[i + 1:i + 3])
        )
        for c in roles:
            if ordinary_phrase and c.role == "body-paragraph":
                contribute(c, config, "body_phrase_between_sentences", 20,
                           "正文常见样式短语夹在完整正文句之间，保留正文身份", context=True)
            if organization_cluster and c.role == "organization-department":
                contribute(c, config, "organization_title_date_cluster", 20,
                           "机构名称位于文前题名之后、日期之前，顺序证据相互印证", context=True)

    hierarchy = resolve_hierarchy(features, candidates, config)
    return {
        "numbering_family_levels": numbering,
        "numbering_conflicts": sorted(conflicts),
        "numbering_corroborated_families": sorted(corroborated),
        "primary_title_element_index": title_index,
        **hierarchy,
    }

