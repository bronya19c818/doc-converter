"""Policy contract tests, authored before the policy implementation.

Failure modes: wrong role family, scored-role takeover, mutable shared rules,
unsafe structure deletion, or an unresolved role being visually rewritten.
"""

import pytest


def test_policy_families_and_absolute_structure_preservation() -> None:
    from doc_converter.docx_direct.transformation_policy import policy_for_role

    structural = [
        "document-title",
        "document-subtitle",
        "author",
        "organization-department",
        "date",
        "table-caption",
        "figure-caption",
        "reference-heading",
    ] + [f"heading-{i}" for i in range(1, 7)]
    for role in structural:
        policy = policy_for_role(role)
        expected = "heading-strong" if role.startswith("heading-") else (
            "caption-strong" if role.endswith("-caption") else "structural-metadata"
        )
        assert policy.family == expected
        assert policy.run_properties["rFonts"] == "replace"
        assert policy.run_properties["b"] == "replace"
    for role in ("body-paragraph", "reference-entry"):
        policy = policy_for_role(role)
        assert policy.family == ("reference-mixed" if role == "reference-entry" else "body-mixed")
        assert policy.run_properties["b"] == "conditional"
        assert policy.run_properties["u"] == "conditional"
    assert policy_for_role("body-table").family == "table-body-mixed"
    assert policy_for_role("unexpected-role").family == "preserve"
    assert policy_for_role("heading-1", action="uncertain").family == "preserve"
    for role in structural + ["body-paragraph", "body-table", "unknown"]:
        policy = policy_for_role(role)
        assert policy.run_properties["vertAlign"] == "preserve"
        assert policy.paragraph_properties["numPr"] == "preserve"
        assert {
            "hyperlink",
            "footnoteReference",
            "endnoteReference",
            "bookmarkStart",
            "fldChar",
            "instrText",
            "drawing",
            "oMath",
            "br",
            "tab",
            "ins",
            "del",
        } <= set(policy.protected_structures)
    with pytest.raises(TypeError):
        policy_for_role("body-paragraph").run_properties["b"] = "discard"
