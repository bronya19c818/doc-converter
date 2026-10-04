"""Explicit immutable role policies, independent of semantic recognition."""

from __future__ import annotations

from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict

from doc_converter.docx_direct.model import Action

PropertyMode = Literal["replace", "preserve", "discard", "conditional"]
PolicyFamily = Literal["structural-strong", "body-mixed", "table-body", "preserve"]

# Executors only change allowed formatting nodes; these are never removed.
PROTECTED_STRUCTURES = (
    "hyperlink",
    "footnoteReference",
    "endnoteReference",
    "bookmarkStart",
    "bookmarkEnd",
    "fldSimple",
    "fldChar",
    "instrText",
    "drawing",
    "pict",
    "object",
    "oMath",
    "oMathPara",
    "tab",
    "br",
    "lastRenderedPageBreak",
    "ins",
    "del",
    "moveFrom",
    "moveTo",
    "numPr",
    "sectPr",
    "tbl",
    "tr",
    "tc",
    "gridSpan",
    "vMerge",
)


class PropertyRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    property: str
    mode: PropertyMode


class TransformationPolicy(BaseModel):
    """A visual policy with structural preservation invariant in the executor."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    family: PolicyFamily
    paragraph_rules: tuple[PropertyRule, ...]
    run_rules: tuple[PropertyRule, ...]
    protected_structures: tuple[str, ...] = PROTECTED_STRUCTURES

    @property
    def paragraph_properties(self) -> Mapping[str, PropertyMode]:
        return MappingProxyType({r.property: r.mode for r in self.paragraph_rules})

    @property
    def run_properties(self) -> Mapping[str, PropertyMode]:
        return MappingProxyType({r.property: r.mode for r in self.run_rules})


def _policy(
    family: PolicyFamily, *, strong: bool = False, table: bool = False, preserve: bool = False
) -> TransformationPolicy:
    paragraph: dict[str, PropertyMode] = {
        "pStyle": "replace",
        "jc": "replace",
        "ind": "conditional",
        "spacing": "replace",
        "keepNext": "preserve" if table else "replace",
        "pageBreakBefore": "preserve",
        "numPr": "preserve",
        "outlineLvl": "preserve",
    }
    run: dict[str, PropertyMode] = {
        "rFonts": "replace",
        "sz": "replace",
        "szCs": "replace",
        "b": "replace" if strong else "conditional",
        "bCs": "replace" if strong else "conditional",
        "i": "replace" if strong else "conditional",
        "iCs": "replace" if strong else "conditional",
        "color": "replace" if strong else "conditional",
        "u": "conditional",
        "highlight": "conditional",
        "vertAlign": "preserve",
        "rStyle": "conditional",
    }
    if preserve:
        paragraph = {k: "preserve" for k in paragraph}
        run = {k: "preserve" for k in run}
    return TransformationPolicy(
        name=family,
        family=family,
        paragraph_rules=tuple(PropertyRule(property=k, mode=v) for k, v in paragraph.items()),
        run_rules=tuple(PropertyRule(property=k, mode=v) for k, v in run.items()),
    )


STRUCTURAL_STRONG_POLICY = _policy("structural-strong", strong=True)
BODY_MIXED_POLICY = _policy("body-mixed")
TABLE_BODY_POLICY = _policy("table-body", table=True)
PRESERVE_POLICY = _policy("preserve", preserve=True)

_ROLE_POLICIES = {
    **dict.fromkeys(
        (
            "document-title",
            "document-subtitle",
            "author",
            "organization-department",
            "date",
            "table-caption",
            "figure-caption",
            "reference-heading",
            *(f"heading-{i}" for i in range(1, 7)),
        ),
        STRUCTURAL_STRONG_POLICY,
    ),
    **dict.fromkeys(("body-paragraph", "reference-entry"), BODY_MIXED_POLICY),
    **dict.fromkeys(("body-table", "table-row-header", "table-column-header"), TABLE_BODY_POLICY),
}


def policy_for_role(role: str, *, action: Action = "mapped") -> TransformationPolicy:
    """Only legacy mapped roles may enter visual rewriting."""

    return _ROLE_POLICIES.get(role, PRESERVE_POLICY) if action == "mapped" else PRESERVE_POLICY
