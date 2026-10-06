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

LEVELS = ("HIGH", "P1", "P2", "SAMPLE")
STRUCTURAL_ROLES = {
    "document-title", "document-subtitle", "author", "organization-department", "date",
    *(f"heading-{i}" for i in range(1, 7)), "table-caption", "figure-caption", "reference-heading",
}


def review_risks(
    analysis: dict[str, Any], report: dict[str, Any], *, levels: list[str] | None = None,
    max_per_flag: int | None = None, full: bool = False,
) -> dict[str, Any]:
    if levels is not None and any(level not in LEVELS for level in levels):
        raise ValueError("未知风险等级")
    if max_per_flag is not None and max_per_flag < 1:
        raise ValueError("抽样限额必须为正整数")
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
        flags: list[str] = []
        priorities: list[str] = []
        if source == "scored" and mapped:
            flags.append("scored_takeover")
            priorities.append("P1" if decision["role"] in STRUCTURAL_ROLES else "P2")
        if f.get("region") == "preface" and heading and mapped:
            flags.append("preface_heading")
            priorities.append("P1")
        if heading and mapped and f.get("literal_numbering") and f.get("text_length", 0) <= 20 \
                and f.get("table_context") is None:
            flags.append("short_numbered_heading")
            priorities.append("P1")
        if source == "scored" and heading and f.get("numbering_family") \
                and (element.get("legacy_decision") or {}).get("role") != decision["role"]:
            flags.append("numbering_level_changed")
            priorities.append("P1")
        complex_object = any(f.get(k) or element.get(k) for k in (
            "has_complex_object", "has_embedded_object", "has_math", "has_field", "has_drawing",
        ))
        if complex_object and mapped:
            flags.append("complex_object_mapped")
            priorities.append("HIGH")
        metadata_conflict = mapped and heading and f.get("native_heading_level") is not None and any(f.get(k) for k in (
            "person_name_pattern", "author_name_list_pattern", "organization_pattern", "explicit_date",
        ))
        if metadata_conflict:
            flags.append("native_heading_metadata_conflict")
            priorities.append("HIGH")
        score = decision.get("score")
        if mapped and isinstance(score, (int, float)) and score >= high_score and f.get("text_length", 0) <= 20:
            flags.append("high_confidence_short_text")
            priorities.append("SAMPLE")
        if not flags:
            continue
        risks.append({
            "element_id": element["element_id"], "text": element["text"],
            "document_order": element.get("document_order", index),
            "context_before": [e["text"] for e in elements[max(0, index - 2):index]],
            "context_after": [e["text"] for e in elements[index + 1:index + 3]],
            "features": f,
            "legacy_decision": element.get("legacy_decision"),
            "scored_decision": element.get("scored_decision"),
            "selected_decision": decision,
            "selection_source": source, "selection_reason": element.get("selection_reason"),
            "policy_name": record.get("policy_name"), "transform_safety": record.get("transform_safety"),
            "risk_level": min(priorities, key=LEVELS.index), "risk_flags": flags,
        })
    risks.sort(key=lambda e: (LEVELS.index(e["risk_level"]), e["document_order"], e["element_id"]))
    hits = Counter(e["risk_level"] for e in risks)
    emitted = []
    signature_counts: Counter[tuple[Any, ...]] = Counter()
    for e in risks:
        level = e["risk_level"]
        if levels is not None and level not in levels:
            continue
        table_body = e["selected_decision"]["role"] == "body-table" and e["features"].get("table_context") is not None
        signature = (level, e["selection_source"], e["selected_decision"]["role"], tuple(e["risk_flags"]))
        limit = max_per_flag if max_per_flag is not None else (
            10 if table_body and level == "P2" else 20 if level == "P2"
            else 5 if table_body and e["selection_source"] == "agreement" else 10
        )
        if full or level in {"HIGH", "P1"} or signature_counts[signature] < limit:
            emitted.append(e)
            signature_counts[signature] += 1
    counts = Counter(e["risk_level"] for e in emitted)
    return {
        "source_sha256": analysis.get("source_sha256"),
        "classification_mode": analysis.get("classification_mode"),
        "review_scope": "风险筛选，不自动修改决策，不代替人工语义验收",
        "missing_feature_fields": sorted(missing_fields),
        "sampling": {"levels": levels or list(LEVELS), "full": full,
                     "max_per_flag": max_per_flag, "strategy": "document_order then element_id, per level/source/role/flags signature"},
        "summary": {"total_analyzed": len(elements), "analyzed": len(elements), "flagged": len(risks),
                    "high": hits["HIGH"], "high_risk": hits["HIGH"], "p1": hits["P1"],
                    "p2_total": hits["P2"], "p2_sampled": counts["P2"],
                    "sample_total": hits["SAMPLE"], "sample_emitted": counts["SAMPLE"],
                    "emitted": len(emitted), "emitted_by_level": {k: counts[k] for k in LEVELS},
                    "risk_flag_counts": dict(Counter(flag for e in risks for flag in e["risk_flags"]))},
        "elements": emitted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--level", choices=LEVELS, action="append", help="可重复选择；命中总量仍包含所有等级")
    parser.add_argument("--max-per-flag", type=int, help="覆盖 P2/SAMPLE 每种风险签名的限额")
    parser.add_argument("--full", action="store_true", help="不抽样，仍遵循 --level")
    args = parser.parse_args()
    if args.max_per_flag is not None and args.max_per_flag < 1:
        parser.error("--max-per-flag 必须大于零")
    output = args.output or args.report.parent / "decision-risk-review.json"
    inputs = {args.analysis.resolve(), args.report.resolve()}
    if output.resolve() in inputs or args.markdown and args.markdown.resolve() in inputs:
        parser.error("风险输出不能覆盖输入审计")
    if args.markdown and args.markdown.resolve() == output.resolve():
        parser.error("JSON 与 Markdown 输出路径不能相同")
    result = review_risks(json.loads(args.analysis.read_text(encoding="utf-8")),
                          json.loads(args.report.read_text(encoding="utf-8")),
                          levels=args.level, max_per_flag=args.max_per_flag, full=args.full)
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
                          "风险：" + ", ".join(e["risk_flags"]), "", "判断：", ""])
            for name in ("legacy", "scored", "selected"):
                d = e.get(name + "_decision") or {}
                lines.append(f"- {name}: {d.get('role')} / {d.get('action')}")
            d = e["selected_decision"]
            lines.extend(["", "关键证据：", "",
                          f"- numbering_family = {e['features'].get('numbering_family')}",
                          f"- score = {d.get('score')}; margin = {d.get('margin')}",
                          f"- selection_source = {e['selection_source']}",
                          f"- selection_reason = {e['selection_reason']}", ""])
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
