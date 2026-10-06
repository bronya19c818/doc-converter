"""Choose semantics without writing XML or deciding transformation safety."""

from __future__ import annotations

from doc_converter.docx_direct.model import (
    ClassificationDecision,
    DecisionMode,
    ElementAnalysis,
    SelectionSource,
)
from doc_converter.docx_direct.scoring import ScoringConfig


def is_strong_legacy_anchor(element: ElementAnalysis) -> bool:
    """Require analyzer/context anchors; a bare numbering regex is insufficient."""

    legacy = element.legacy_decision
    f = element.features
    if legacy is None or legacy.action != "mapped" or not f:
        return False
    if f["list"] or any(f[k] for k in ("has_field", "has_drawing", "has_manual_break")):
        return False
    if f["table_context"] is not None:
        return legacy.role == "body-table"
    if legacy.role == f"heading-{f['native_heading_level']}" and not f["body_sentence"]:
        return True
    labels = {"author": "explicit_author_label",
              "organization-department": "explicit_organization_label", "date": "explicit_date"}
    if legacy.role in labels:
        return bool(f["is_preface"] and f[labels[legacy.role]])
    if legacy.role in {"table-caption", "figure-caption"}:
        expected = {"表", "table"} if legacy.role == "table-caption" else {"图", "figure"}
        return bool(f["caption_pattern"] in expected or element.signals.get("caption_credit"))
    return bool(
        legacy.role == "reference-heading" and f["reference_boundary"]
        or legacy.role == "reference-entry" and f["is_postface"]
    )


def select_decision(
    element: ElementAnalysis, config: ScoringConfig, mode: DecisionMode = "hybrid",
) -> tuple[ClassificationDecision, SelectionSource, str]:
    """Return an independent decision plus a deterministic, auditable selection."""

    if mode not in {"legacy", "shadow", "hybrid", "scored"}:
        raise ValueError(f"未知 decision mode：{mode}")
    legacy, scored = element.legacy_decision, element.scored_decision

    def choose(
        d: ClassificationDecision, source: SelectionSource, reason: str,
    ) -> tuple[ClassificationDecision, SelectionSource, str]:
        return d.model_copy(deep=True), source, reason

    def preserve(reason: str) -> tuple[ClassificationDecision, SelectionSource, str]:
        d = scored or ClassificationDecision(role="unknown", confidence=0, action="preserved")
        return d.model_copy(update={"action": "preserved"}, deep=True), "preserve", reason

    if mode in {"legacy", "shadow"}:
        return (choose(legacy, "legacy", f"{mode} regression mode") if legacy
                else preserve("legacy decision unavailable"))
    if mode == "scored":
        return (choose(scored, "scored", "experimental scored mode") if scored
                else preserve("scored decision unavailable"))

    conflicts = {"hierarchy_jump", "numbering_anchor_conflict"}
    if any(e.feature in conflicts for c in element.candidates for e in c.evidence):
        return preserve("resolver reported conflicting hierarchy evidence")
    if scored is not None:
        if scored.margin is not None and scored.margin < config.ambiguous_margin:
            return preserve("scored evidence is ambiguous; legacy fallback forbidden")
        if legacy and (legacy.role, legacy.action) == (scored.role, scored.action):
            return choose(scored, "agreement", "legacy and scored role/action agree")
        if (scored.action == "mapped" and scored.confidence_band == "high"
                and scored.score is not None and scored.score >= config.high_score
                and scored.margin is not None and scored.margin >= config.high_margin):
            return choose(scored, "scored", "scored high confidence and sufficient margin")
        if scored.confidence_band == "medium":
            if legacy and scored.role != "unknown" and scored.role == legacy.role \
                    and legacy.action == "mapped":
                return choose(scored, "agreement", "medium-confidence role agreement")
            return preserve("medium-confidence disagreement")
        # Unknown supported by actual structural evidence is a judgment, not failure.
        if scored.top_role == "unknown" or scored.role != "unknown":
            return preserve("scored conservative judgment; legacy fallback forbidden")
    if is_strong_legacy_anchor(element):
        assert legacy is not None
        return choose(legacy, "legacy", "no effective scored candidate; strong legacy anchor")
    return preserve("no effective scored candidate and no strong legacy anchor")
