"""Source-backed DOCX -> application API -> output/audit acceptance artifacts."""

from __future__ import annotations

import json
import os
from collections import Counter
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from docx.oxml.ns import qn
from lxml import etree

from doc_converter.docx_direct.analyzer import _iter_paragraphs
from doc_converter.docx_styles import ROLE_TO_STYLE_ID
from doc_converter.style_library import create_style_pack
from scripts.verify_docx_shadow import convert, part_hashes

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/docx_direct_acceptance"
PRESSURE = ROOT / "tests/fixtures/DOCX转Markdown压力测试_V1_结构兼容性.docx"
PROTECTED = (
    "numPr", "tblPr", "tblGrid", "gridSpan", "vMerge", "tcPr", "trPr", "br", "tab",
    "vertAlign", "sectPr", "drawing", "bookmarkStart", "bookmarkEnd", "fldChar",
    "instrText", "footnoteReference", "endnoteReference", "ins", "del",
)


def verify_structure(source: Path, output: Path) -> dict:
    before, after = part_hashes(source), part_hashes(output)
    assert before.keys() == after.keys(), "DOCX ZIP member 集合变化"
    changed = sorted(name for name in before if before[name] != after[name])
    assert set(changed) <= {"word/document.xml", "word/styles.xml"}, changed
    with ZipFile(source) as old, ZipFile(output) as new:
        roots = [etree.fromstring(z.read("word/document.xml")) for z in (old, new)]
        texts = [
            ["".join(n.text or "" for n in p.iter() if n.tag in {qn("w:t"), qn("w:delText")})
             for p in root.iter(qn("w:p"))]
            for root in roots
        ]
        assert texts[0] == texts[1], "可见文本或段落顺序变化"
        for tag in PROTECTED:
            signatures = [
                [etree.tostring(n, method="c14n", exclusive=True)
                 for n in root.iter(qn("w:" + tag))]
                for root in roots
            ]
            assert signatures[0] == signatures[1], tag
        # Hyperlink runs can change base font, but their relationships/anchor cannot.
        assert [[dict(n.attrib) for n in root.iter(qn("w:hyperlink"))] for root in roots][0] == [
            dict(n.attrib) for n in roots[1].iter(qn("w:hyperlink"))
        ]
        paragraphs = [list(root.iter(qn("w:p"))) for root in roots]
        source_styles = etree.fromstring(old.read("word/styles.xml"))
        target_styles = etree.fromstring(new.read("word/styles.xml"))
        lookup = {s.get(qn("w:styleId")): s for s in target_styles.findall(qn("w:style"))}
        for s in source_styles.findall(qn("w:style")):
            assert etree.tostring(s, method="c14n", exclusive=True) == etree.tostring(
                lookup[s.get(qn("w:styleId"))], method="c14n", exclusive=True,
            ), "原有样式定义变化"
    return {"changed_parts": changed, "paragraphs": len(paragraphs[0]),
            "text_order_preserved": True, "protected_structure_preserved": True}


def verify_sample(source: Path, output: Path, truth: list[dict], mode: str = "hybrid") -> dict:
    source_hash = sha256(source.read_bytes()).hexdigest()
    pack = create_style_pack(name="Selected decision 验收", format_id="docx")
    convert(source, output, pack, decision_mode=mode)
    report = json.loads((output / "docx-normalization-report.json").read_text(encoding="utf-8"))
    analysis = json.loads((output / "docx-analysis.json").read_text(encoding="utf-8"))
    target = next(output.glob("*.docx"))
    summary = {"source": source.name, "mode": mode, "source_sha256": source_hash,
               "comparisons": [], "passed": False}
    try:
        assert sha256(source.read_bytes()).hexdigest() == source_hash
        summary["structure"] = verify_structure(source, target)
        assert analysis["classification_mode"] == mode
        for e in analysis["elements"]:
            assert e.get("selected_decision"), f"缺少 selected decision: {e['text']}"
            assert e["legacy_decision"] and e["scored_decision"]
            assert e["role"] == e["legacy_decision"]["role"]
            assert e["action"] == e["legacy_decision"]["action"]
            assert e["selection_source"] and e["selection_reason"]
        for t in truth:
            matches = [e for e in analysis["elements"] if e["text"] == t["text"]]
            assert len(matches) == 1, t["text"]
            e = matches[0]
            comparison = {"text": t["text"], "expected": t,
                          **{k: e[k] for k in ("legacy_decision", "scored_decision",
                                              "selected_decision", "selection_source")}}
            summary["comparisons"].append(comparison)
        if mode == "hybrid":
            for c in summary["comparisons"]:
                assert c["selected_decision"]["role"] == c["expected"]["role"], c
                if "action" in c["expected"]:
                    assert c["selected_decision"]["action"] == c["expected"]["action"], c
                if c["expected"]["role"].startswith("heading-") or c["expected"]["role"] in {
                    "document-title", "document-subtitle", "table-caption", "figure-caption",
                    "reference-heading",
                }:
                    e = next(e for e in analysis["elements"] if e["text"] == c["text"])
                    assert c["selected_decision"]["action"] == "mapped", c
                    assert e["element_id"] in report["xml_patch"]["modified_element_ids"], c
        with ZipFile(source) as old, ZipFile(target) as new:
            roots = [etree.fromstring(z.read("word/document.xml")) for z in (old, new)]
            paragraph_nodes = [
                {path: p for p, path, _ in _iter_paragraphs(root.find(qn("w:body")))}
                for root in roots
            ]
            executed, skipped = 0, 0
            modified_ids = set(report["xml_patch"]["modified_element_ids"])
            assert len(modified_ids) == len(report["xml_patch"]["modified_element_ids"])
            # Analyzer xml paths start inside w:body, including nested cell paragraphs.
            for e, record in zip(analysis["elements"], report["elements"], strict=True):
                nodes = [lookup[tuple(e["xml_path"])] for lookup in paragraph_nodes]
                d = e["selected_decision"]
                assert record["selected_decision"] == d
                assert record["detected_role"] == d["role"]
                assert record["action"] == d["action"]
                assert record["policy_name"] and record["transform_safety"]
                if d["action"] != "mapped":
                    assert e["element_id"] not in modified_ids
                    assert etree.tostring(nodes[0], method="c14n", exclusive=True) == etree.tostring(
                        nodes[1], method="c14n", exclusive=True,
                    ), e["text"]
                elif e["element_id"] in modified_ids:
                    executed += 1
                    assert record["transform_safety"] != "preserve"
                    style = nodes[1].find("w:pPr/w:pStyle", roots[1].nsmap)
                    assert style is not None and style.get(qn("w:val")) == ROLE_TO_STYLE_ID[d["role"]]
                else:
                    skipped += 1
                    assert record["transform_safety"] == "preserve"
                    assert record["skipped_properties"] and all(
                        p["reason"] for p in record["skipped_properties"]
                    ), e["text"]
                    assert etree.tostring(nodes[0], method="c14n", exclusive=True) == etree.tostring(
                        nodes[1], method="c14n", exclusive=True,
                    ), e["text"]
            assert executed == len(modified_ids) == report["xml_patch"]["mapped_count"]
            assert skipped == report["xml_patch"]["skipped_count"]
            if executed == 0:
                assert old.read("word/document.xml") == new.read("word/document.xml")
        expected_counts = dict(Counter(e["selected_decision"]["action"] for e in analysis["elements"]))
        for action in ("mapped", "uncertain", "preserved"):
            assert report["classification"]["selected_counts"][action] == expected_counts.get(action, 0)
        assert report["counts"]["mapped"] == len(report["xml_patch"]["modified_element_ids"])
        assert sum(report["counts"].values()) == len(analysis["elements"])
        summary["passed"] = True
        return summary
    finally:
        (output / "verification.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )


def verify_suite(output: Path, mode: str = "hybrid", *, with_preview: bool = False) -> dict:
    if not with_preview:
        os.environ["DOC_CONVERTER_LIBREOFFICE"] = str(ROOT / "artifacts/no-preview-engine")
    output.mkdir(parents=True, exist_ok=False)
    truth = json.loads((FIXTURES / "ground_truth.json").read_text(encoding="utf-8"))["files"]
    results = [verify_sample(FIXTURES / name, output / Path(name).stem, t, mode)
               for name, t in truth.items()]
    results.append(verify_sample(PRESSURE, output / "pressure", [], mode))
    summary = {"passed": True, "decision_mode": mode, "fixtures": results,
               "ground_truth_paragraphs": sum(len(t) for t in truth.values())}
    (output / "verification.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return summary
