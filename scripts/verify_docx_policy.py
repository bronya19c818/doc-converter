"""Repeatable DOCX conversion-policy acceptance with durable artifacts.

Run: .venv/Scripts/python scripts/verify_docx_policy.py --output artifacts/policy-acceptance
Also run verify_docx_shadow.py --policy-output against the phase-one baseline.
"""

from __future__ import annotations

import argparse
import json
import os
import runpy
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from docx.oxml.ns import qn
from lxml import etree
from verify_docx_shadow import check_shadow, convert, structure_signature

from doc_converter.style_library import create_style_pack

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        default=[],
        help="额外真实 DOCX，可重复传入；原文件只读",
    )
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    os.environ["DOC_CONVERTER_LIBREOFFICE"] = str(ROOT / "artifacts/no-preview-engine")
    acceptance = runpy.run_path(str(ROOT / "tests/test_docx_direct_policy_conversion.py"))
    generated = acceptance["verify_policy_conversion"](folder / "complex-policy")
    inherited = folder / "inherited-policy"
    inherited.mkdir()
    acceptance["test_inherited_numbering_and_page_break_survive_style_mapping"](inherited)
    fields = folder / "field-policy"
    fields.mkdir()
    acceptance["test_complex_field_results_across_paragraphs_are_untouched"](fields)
    sources = [ROOT / "tests/fixtures/DOCX转Markdown压力测试_V1_结构兼容性.docx", *args.source]
    results = []
    for index, source in enumerate(sources):
        source = source.resolve()
        original_hash = sha256(source.read_bytes()).hexdigest()
        case = folder / f"source-{index + 1}"
        result = convert(source, case, create_style_pack(name="策略压力验收", format_id="docx"))
        assert result["source_sha256"] == original_hash == sha256(source.read_bytes()).hexdigest()
        normalized = next(case.glob("*.docx"))
        with ZipFile(source) as old, ZipFile(normalized) as new:
            assert set(old.namelist()) == set(new.namelist())
            for member in old.namelist():
                if member not in {"word/document.xml", "word/styles.xml"}:
                    assert old.read(member) == new.read(member), member
            roots = [etree.fromstring(z.read("word/document.xml")) for z in (old, new)]
            assert structure_signature(roots[0]) == structure_signature(roots[1])
            for tag in (
                "fldSimple",
                "drawing",
                "pict",
                "object",
                "ins",
                "del",
                "moveFrom",
                "moveTo",
            ):
                assert [
                    etree.tostring(n, method="c14n", exclusive=True)
                    for n in roots[0].iter(qn("w:" + tag))
                ] == [
                    etree.tostring(n, method="c14n", exclusive=True)
                    for n in roots[1].iter(qn("w:" + tag))
                ], tag
        paragraphs = check_shadow(case, {})
        report = json.loads((case / "docx-normalization-report.json").read_text(encoding="utf-8"))
        assert all(e["policy_name"] and e["transform_safety"] for e in report["elements"])
        results.append(
            {
                "source": str(source),
                "source_sha256": original_hash,
                "paragraphs": paragraphs,
                "protected_parts_unchanged": True,
                "policies": report["transformation_policy_counts"],
            }
        )
    summary = {
        "passed": True,
        "generated": generated,
        "inherited_structures": True,
        "cross_paragraph_fields": True,
        "sources": results,
    }
    (folder / "verification.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
