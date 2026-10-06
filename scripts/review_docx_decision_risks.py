"""Read-only risk triage of matching DOCX analysis and execution audit files.

Flags are review candidates, not new classification decisions or ground truth.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


def review_risks(analysis: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    if any(not isinstance(value := item.get("source_sha256"), str)
           or not re.fullmatch(r"[0-9a-fA-F]{64}", value) for item in (analysis, report)):
        raise ValueError("analysis 与 report 均须提供有效 SHA-256 指纹")
    if analysis.get("source_sha256") != report.get("source_sha256"):
        raise ValueError("analysis 与 report 的源文件指纹不一致")
    if analysis.get("classification_mode") != report.get("classification_mode") \
            or analysis.get("scoring_config") != report.get("scoring_config"):
        raise ValueError("analysis 与 report 的选择模式或评分配置不一致")
    elements = analysis["elements"]
    records = {e["element_id"]: e for e in report["elements"]}
    ids = [e["element_id"] for e in elements]
    if len(records) != len(report["elements"]) or len(set(ids)) != len(ids) or set(ids) != set(records):
        raise ValueError("analysis 与 report 的 element_id 不一致或重复")
    high_score = analysis.get("scoring_config", {}).get("high_score", 85)
    risks = []
    missing_fields: set[str] = set()
    for index, element in enumerate(elements):
        record = records[element["element_id"]]
        decision = element.get("selected_decision")
        if decision is None or decision != record.get("selected_decision"):
            raise ValueError(f"selected decision 不一致：{element['element_id']}")
        f = element.get("features", {})
        missing_fields.update(k for k in ("author_name_list_pattern", "has_embedded_object", "has_math")
                              if k not in f)
        mapped = decision["action"] == "mapped"
        heading = decision["role"].startswith("heading-")
        source = element.get("selection_source")
        flags = []
        if source == "scored" and mapped:
            flags.append("scored_takeover")
        if f.get("region") == "preface" and heading:
            flags.append("preface_heading")
        if heading and f.get("literal_numbering") and f.get("text_length", 0) <= 20:
            flags.append("short_numbered_heading")
        complex_object = any(f.get(k, element.get(k, False)) for k in (
            "has_embedded_object", "has_math", "has_field", "has_drawing",
        ))
        if complex_object and mapped:
            flags.append("complex_object_mapped")
        metadata_conflict = f.get("native_heading_level") is not None and any(f.get(k) for k in (
            "person_name_pattern", "author_name_list_pattern", "organization_pattern", "explicit_date",
        ))
        if metadata_conflict:
            flags.append("native_heading_metadata_conflict")
        score = decision.get("score")
        if mapped and isinstance(score, (int, float)) and score >= high_score and f.get("text_length", 0) <= 20:
            flags.append("high_confidence_short_text")
        if not flags:
            continue
        high = "complex_object_mapped" in flags or metadata_conflict and heading and mapped
        risks.append({
            "element_id": element["element_id"], "text": element["text"],
            "context_before": [e["text"] for e in elements[max(0, index - 2):index]],
            "context_after": [e["text"] for e in elements[index + 1:index + 3]],
            "features": f,
            "legacy_decision": element.get("legacy_decision"),
            "scored_decision": element.get("scored_decision"),
            "selected_decision": decision,
            "selection_source": source, "selection_reason": element.get("selection_reason"),
            "policy_name": record.get("policy_name"), "transform_safety": record.get("transform_safety"),
            "risk_level": "HIGH" if high else "REVIEW", "risk_flags": flags,
        })
    risks.sort(key=lambda e: (e["risk_level"] != "HIGH", e["selection_source"] != "scored"))
    return {
        "source_sha256": analysis.get("source_sha256"),
        "classification_mode": analysis.get("classification_mode"),
        "review_scope": "风险筛选，不自动修改决策，不代替人工语义验收",
        "missing_feature_fields": sorted(missing_fields),
        "summary": {"analyzed": len(elements), "flagged": len(risks),
                    "high_risk": sum(e["risk_level"] == "HIGH" for e in risks),
                    "risk_flag_counts": dict(Counter(flag for e in risks for flag in e["risk_flags"]))},
        "elements": risks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    output = args.output or args.report.parent / "decision-risk-review.json"
    inputs = {args.analysis.resolve(), args.report.resolve()}
    if output.resolve() in inputs or args.markdown and args.markdown.resolve() in inputs:
        parser.error("风险输出不能覆盖输入审计")
    if args.markdown and args.markdown.resolve() == output.resolve():
        parser.error("JSON 与 Markdown 输出路径不能相同")
    result = review_risks(json.loads(args.analysis.read_text(encoding="utf-8")),
                          json.loads(args.report.read_text(encoding="utf-8")))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        lines = ["# DOCX 决策风险抽查", "", str(result["summary"]), "",
                 "以下为待核验决策，不表示已确认误判。", ""]
        for e in result["elements"]:
            lines.extend([f"## {e['risk_level']} · {e['element_id']}", "",
                          f"正文：{e['text']}", "",
                          "前文：" + " / ".join(e["context_before"]), "",
                          "后文：" + " / ".join(e["context_after"]), "",
                          "风险：" + ", ".join(e["risk_flags"]), "",
                          "```json", json.dumps(e, ensure_ascii=False, indent=2), "```", ""])
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
