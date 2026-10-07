"""Repeatable actual-DOCX role conversion acceptance, retaining all packages/audits."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]


def load_tests(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / (name + ".py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load DOCX acceptance contracts")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_roles(output: Path) -> dict:
    if output.exists():
        raise ValueError("Use a fresh acceptance artifact directory")
    output.mkdir(parents=True)
    contracts = load_tests("test_docx_role_transformation_v2")
    cases: list[tuple[str, Callable[..., Any], tuple[Any, ...]]] = [
        ("outline-upsert", contracts.test_visual_outline_and_managed_style_upsert_end_to_end, ()),
        ("dirty-h6-to-h3", contracts.test_dirty_heading_peer_recovery_applies_actual_outline, ()),
        ("explicit-table-header", contracts.test_only_explicit_nearest_table_header_is_selected, ()),
        ("unsafe-label", contracts.test_unsafe_inline_label_boundary_preserves_paragraph, ()),
        ("metadata-link-field", contracts.test_composite_content_link_and_field_are_not_reconstructed, ()),
        ("semantic-inheritance", contracts.test_inline_character_inheritance_keeps_semantic_layers, ()),
        ("protected-inherited-format", contracts.test_protected_inherited_field_format_preserves_whole_paragraph, ()),
        ("default-numbering-true", contracts.test_default_style_true_inherited_numbering_is_kept, ()),
        ("complex-script-local", contracts.test_complex_script_emphasis_is_audited_per_run, ()),
        ("managed-protected-style", contracts.test_managed_style_used_by_protected_field_is_not_indirectly_rewritten, ()),
        ("content-toggle-baseline", contracts.test_content_character_toggle_resets_bold_label_baseline, ()),
        ("heading-document-default-on", contracts.test_heading_bold_overrides_document_default_toggle, (True,)),
        ("heading-document-default-off", contracts.test_heading_bold_overrides_document_default_toggle, (False,)),
        ("math-complex-font", contracts.test_math_inherited_complex_font_blocks_managed_upsert, ()),
    ]
    for label in ("摘要：", "关键词:"):
        for split in (False, True):
            cases.append((f"metadata-{label[:2]}-{split}", contracts.test_composite_metadata_and_character_projection, (label, split)))
    passed = []
    for name, function, args in cases:
        folder = output / name
        folder.mkdir()
        function(folder, *args)
        passed.append(name)
    policy = load_tests("test_docx_direct_policy_conversion")
    for mode in ("hybrid", "shadow"):
        policy.verify_policy_conversion(output / ("complex-policy-" + mode), mode)
        passed.append("complex-policy-" + mode)
    summary = {"passed": True, "cases": passed, "count": len(passed)}
    (output / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(verify_roles(parser.parse_args().output), ensure_ascii=False))
