"""Offline business-rule review of existing DOCX/API artifacts; never edits Word."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.review_docx_decision_risks import review_risks  # noqa: E402

Target = tuple[dict[str, Any], int, str | None]
Signature = tuple[list[Target], list[str]]


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def confirmation(entry: dict[str, Any], base: Path) -> None:
    reference = entry.get("confirmation_reference")
    digest = entry.get("confirmation_sha256")
    if not isinstance(reference, str) or not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
        raise ValueError("confirmation reference and SHA-256 are required")
    path = Path(reference)
    path = path if path.is_absolute() else base / path
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != digest.lower():
        raise ValueError("confirmation reference missing or fingerprint mismatch")


def identities(rows: list[dict[str, Any]], case_key: str) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    for row in rows:
        key = row[case_key], row["element_id"]
        if key in result:
            raise ValueError("duplicate review identity")
        result[key] = row
    return result


def expectation(entry: dict[str, Any], *, gt: bool = False) -> tuple[Any, Any, Any]:
    return entry["expected_role"], entry["expected_action"], entry["parent_element_id" if gt else "expected_parent_id"]


def compatible(a: tuple[Any, Any, Any], b: tuple[Any, Any, Any]) -> bool:
    return a[:2] == b[:2] and (a[2] is None or b[2] is None or a[2] == b[2])


def executed(e: dict[str, Any], modified: set[str], expected: tuple[Any, Any, Any]) -> bool:
    role, action, parent = expected
    d, f = e["selected_decision"], e["features"]
    return bool(role is not None and (d["role"], d["action"]) == (role, action)
                and ((e["element_id"] in modified) if action == "mapped" else (e["element_id"] not in modified))
                and (parent is None or parent == f["effective_parent_id"]))


def safe(e: dict[str, Any]) -> bool:
    f = e["features"]
    return f.get("table_context") is None and not f.get("has_complex_object")


def title(e: dict[str, Any]) -> str:
    value = e["text"]
    if e["features"]["numbering_family"] == "ARABIC_ENUM":
        value = re.sub(r"^\d+[.、．]?\s*", "", value)
    return re.sub(r"\s+", "", value)


def scopes(elements: list[dict[str, Any]], parent_text: str) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    for start, root in enumerate(elements):
        f = root["features"]
        if root["text"] != parent_text or not safe(root) or f["numbering_family"] != "CN_ENUM":
            continue
        end = next((i for i in range(start + 1, len(elements)) if safe(elements[i]) and (
            elements[i]["features"]["numbering_family"] == "CN_ENUM"
            or elements[i]["features"].get("hierarchy_reset_marker"))), len(elements))
        block = elements[start:end]
        if any(e["features"].get("has_section_break") or e["features"].get("reference_boundary") for e in block):
            continue
        yield root, block


def service_signature(root: dict[str, Any], block: list[dict[str, Any]], rule: dict[str, Any]) -> Signature | None:
    siblings = [i for i,e in enumerate(block) if safe(e) and e["text"] == rule["next_sibling_text"]
                and e["features"]["numbering_family"] == "CN_BRACKET" and e["features"]["numbering_path"] == [2]]
    if len(siblings) != 1:
        return None
    members = block[1:siblings[0]]
    entities = [i for i,e in enumerate(members) if safe(e) and e["text"] == rule["entity_text"]
                and e["features"]["numbering_family"] is None]
    if len(entities) != 1:
        return None
    entity_position = entities[0]
    entity = members[entity_position]
    topics = []
    for spec in rule["topics"]:
        found = [(i,e) for i,e in enumerate(members) if i > entity_position and safe(e)
                 and title(e) == re.sub(r"\s+", "", spec["title"])
                 and (e["features"]["numbering_family"] is None
                      or e["features"]["numbering_family"] == "ARABIC_ENUM"
                      and e["features"]["numbering_path"] == [spec["ordinal"]])]
        if len(found) != 1:
            return None
        topics.append((spec["ordinal"], *found[0]))
    if [i for _,i,_ in topics] != sorted(i for _,i,_ in topics):
        return None
    targets: list[Target] = [(entity, 2, root["element_id"])]
    evidence = [root["element_id"], entity["element_id"], block[siblings[0]]["element_id"]]
    for position, (ordinal, start, topic) in enumerate(topics):
        end = topics[position + 1][1] if position + 1 < len(topics) else len(members)
        children = [e for e in members[start+1:end] if safe(e) and e["features"]["numbering_family"] == "DECIMAL"
                    and e["features"]["numbering_path"][:1] == [ordinal]]
        direct = [e for e in children if len(e["features"]["numbering_path"]) == 2]
        if ordinal in rule["body_prefixes"] and not {1,2}.issubset({e["features"]["numbering_path"][1] for e in direct}):
            return None
        expected_series = rule["heading_clause_series"].get(str(ordinal))
        if expected_series:
            headings = [e for e in direct if not e["features"]["body_sentence"]
                        and not e["features"]["has_terminal_punctuation"]]
            if [e["features"]["numbering_path"][1] for e in headings] != expected_series:
                return None
            targets.extend((e, 4, topic["element_id"]) for e in headings)
        targets.append((topic, 3, entity["element_id"]))
        evidence.extend([topic["element_id"], *[e["element_id"] for e in direct]])
    return targets, evidence


def peers_signature(root: dict[str, Any], block: list[dict[str, Any]], rule: dict[str, Any],
                    truths: dict[str, dict[str, Any]]) -> Signature | None:
    peers = [e for e in block[1:] if safe(e) and e["features"]["numbering_family"] == "ARABIC_ENUM"
             and len(e["features"]["numbering_path"]) == 1 and e["features"]["native_heading_level"] == 3]
    if [e["features"]["numbering_path"][0] for e in peers] != rule["peer_ordinals"]:
        return None
    if len({e["original_style_id"] for e in peers}) != 1:
        return None
    owner = next((e for e in peers if e["features"]["numbering_path"] == [rule["anchor_prefix"]]), None)
    anchors = [e for e in block if safe(e) and e["features"]["numbering_family"] == "DECIMAL"
               and e["features"]["numbering_path"] in [[rule["anchor_prefix"],n] for n in rule["anchor_children"]]]
    if owner is None or len(anchors) != len(rule["anchor_children"]):
        return None
    labels = []
    for e in anchors:
        g = truths.get(e["element_id"])
        if g is None or g["review_status"] != "confirmed" or g["expected_action"] != "mapped" \
                or g["parent_element_id"] not in {None, owner["element_id"]}:
            return None
        labels.append(g)
    levels = {int(g["expected_role"].removeprefix("heading-")) - 1 for g in labels}
    if len(levels) != 1:
        return None
    level = levels.pop()
    if rule.get("explicit_peer_level", level) != level:
        raise ValueError("confirmed peer rule conflicts with strict element GT")
    return [(e, level, None) for e in peers], [root["element_id"], *[e["element_id"] for e in peers + anchors]]


def reconcile(cohort: Path, ground_truth: Path, rules_path: Path, previous_path: Path,
              proxy_review: Path | None = None) -> dict[str, Any]:
    cases: dict[str, tuple[dict[str, Any], set[str]]] = {}
    for manifest in sorted(cohort.glob("real-*/summary.json")):
        if not manifest.resolve().is_relative_to(cohort.resolve()):
            raise ValueError("manifest case path is outside cohort")
        for c in read(manifest)["results"]:
            name = c["case"]
            if not isinstance(name, str) or name in {"", ".", ".."} or any(ch in name for ch in "/\\:"):
                raise ValueError("case path must be a single directory name")
            case = manifest.parent.name + "/" + c["case"]
            folder = (cohort / case).resolve()
            if not folder.is_relative_to(cohort.resolve()):
                raise ValueError("case path is outside cohort")
            a = read(folder / "docx-analysis.json")
            report = read(folder / "docx-normalization-report.json")
            review_risks(a, report, levels=["HIGH"])
            if sha256(Path(c["source"]).read_bytes()).hexdigest() != c["source_sha256"] or c["source_sha256"] != a["source_sha256"]:
                raise ValueError("source fingerprint mismatch")
            if case in cases:
                raise ValueError("duplicate source case")
            cases[case] = (a, set(report["xml_patch"]["modified_element_ids"]))
    truth_rows = read(ground_truth)["elements"]
    truths = identities(truth_rows, "source_case")
    for g in truth_rows:
        if g["evidence_origin"] not in {"user_confirmed", "user_confirmed_element"} or g["review_status"] not in {"confirmed", "confirmed_flexible"}:
            raise ValueError("GT requires explicit user element confirmation")
        confirmation(g, ground_truth.parent)
    previous = identities([e for group in read(previous_path)["groups"] for e in group["elements"]], "case")
    proxies = identities(read(proxy_review)["elements"], "case") if proxy_review else {}
    rules = read(rules_path)["rules"]
    derived: dict[tuple[str, str], dict[str, Any]] = {}
    matched, failures = [], []
    if len({rule["rule_id"] for rule in rules}) != len(rules):
        raise ValueError("duplicate business rule identity")
    for rule in rules:
        case = rule["source_case"]
        a, _ = cases[case]
        if rule["source_sha256"] != a["source_sha256"]:
            raise ValueError("rule source fingerprint mismatch")
        if rule["evidence_origin"] != "user_confirmed_rule":
            raise ValueError("rule needs an explicit user confirmation reference")
        confirmation(rule, rules_path.parent)
        if rule["kind"] not in {"service_content", "confirmed_child_peers"}:
            raise ValueError("unsupported business rule kind")
        for root, block in scopes(a["elements"], rule["parent_text"]):
            signature = service_signature(root, block, rule) if rule["kind"] == "service_content" else peers_signature(
                root, block, rule, {id:g for (source,id),g in truths.items() if source == case})
            if signature is None:
                continue
            targets, evidence = signature
            regime = root["features"]["hierarchy_regime_id"]
            if regime is None or any(e["features"]["hierarchy_regime_id"] != regime for e,_,_ in targets):
                continue
            proof = {"rule_id":rule["rule_id"], "source_case":case, "root_id":root["element_id"], "regime_id":regime,
                     "source_sha256":a["source_sha256"], "evidence_element_ids":list(dict.fromkeys(evidence)),
                     "confirmation_reference":rule["confirmation_reference"], "confirmation_sha256":rule["confirmation_sha256"]}
            matched.append(proof)
            for e,level,parent in targets:
                key = case,e["element_id"]
                declaration = {"expected_role":f"heading-{level}", "expected_action":"mapped", "expected_parent_id":parent,
                               "rule_id":rule["rule_id"], "proof":proof, "business_explanation":rule.get("business_explanation")}
                if key in truths and not compatible(expectation(truths[key], gt=True), expectation(declaration)):
                    raise ValueError("business rule conflicts with strict element GT")
                if key in derived and not compatible(expectation(derived[key]), expectation(declaration)):
                    raise ValueError("overlapping business rules conflict")
                if key not in derived or parent is not None:
                    derived[key] = declaration
    records, pending = [], defaultdict(list)
    for case,(a, modified) in sorted(cases.items()):
        for e in a["elements"]:
            key = case,e["element_id"]
            g, derivation, old, proxy = truths.get(key), derived.get(key), previous.get(key), proxies.get(key)
            if g is None and derivation is None and old is None and proxy is None:
                continue
            if g is not None and (g["source_sha256"] != a["source_sha256"] or g["text"] != e["text"]):
                raise ValueError("GT source fingerprint or text mismatch")
            if old is not None and (old["source_sha256"] != a["source_sha256"] or old["text"] != e["text"]):
                raise ValueError("previous review fingerprint or text mismatch")
            if proxy is not None and (proxy["source_sha256"] != a["source_sha256"] or proxy["text"] != e["text"]):
                raise ValueError("proxy review fingerprint or text mismatch")
            d, f = e["selected_decision"], e["features"]
            expected_role = g["expected_role"] if g else derivation["expected_role"] if derivation else None
            origin = "user_confirmed_element" if g else "business_structure_derived" if derivation else "proxy_review" if proxy else "automated_inference"
            flexible = bool(g and g["review_status"] == "confirmed_flexible")
            gt_passed = (d["action"] == "preserved" or d["role"] == "heading-2" and d["action"] == "mapped"
                         and e["element_id"] in modified and bool(f["hierarchy_evidence"])) if flexible else bool(g and executed(e, modified, expectation(g, gt=True)))
            rule_passed = bool(derivation and executed(e, modified, expectation(derivation)))
            passed = (gt_passed if g else True) and (rule_passed if derivation else True) and bool(g or derivation)
            proposal = old.get("recommended_role") if old else proxy.get("proxy_role") if proxy else None
            superseded = proposal is not None and proposal != (expected_role or d["role"])
            record = {"case":case, "source_sha256":a["source_sha256"], "element_id":e["element_id"], "text":e["text"],
                      "evidence_origin":origin, "strict_element_gt":bool(g and not flexible), "flexible_element_gt":flexible,
                      "expected_role":expected_role, "business_expected_role":expected_role, "selected_decision":d,
                      "expected_action":g["expected_action"] if g else derivation["expected_action"] if derivation else None,
                      "strict_gt_expectation":expectation(g, gt=True) if g else None,
                      "rule_expectation":expectation(derivation) if derivation else None,
                      "gt_passed":gt_passed, "rule_passed":rule_passed,
                      "actual_modified":e["element_id"] in modified, "passed":bool(passed),
                      "proposal_status":"superseded" if superseded else "active", "prior_proxy_proposal":proposal,
                      "active_proxy_proposal":None if superseded else proposal,
                      "risk_level":proxy.get("risk_level") if proxy else None,
                      "proxy_review_result":proxy.get("result") if proxy else None,
                      "source_native_heading_level":f["source_native_heading_level"], "effective_heading_level":f["effective_heading_level"],
                      "automated_parent_id":f["effective_parent_id"], "automated_source_defect_type":f["source_defect_type"],
                      **{k:v for k,v in (derivation or {}).items() if not k.startswith("expected_")}}
            records.append(record)
            if (g or derivation) and not passed:
                failures.append(key)
            if not passed and (g or derivation or old):
                root_id = derivation["proof"]["root_id"] if derivation else None
                if root_id is None:
                    nodes = {n["element_id"]:n for n in a["document_baselines"]["heading_tree"]}
                    virtual = {n["virtual_node_id"]:n for n in a["document_baselines"]["virtual_heading_nodes"]}
                    root_id = e["element_id"]
                    while root_id in nodes and nodes[root_id]["parent_id"]:
                        parent_id = nodes[root_id]["parent_id"]
                        root_id = virtual[parent_id]["parent_id"] if parent_id in virtual else parent_id
                pending[case,root_id].append(record)
    if (set(truths) | set(previous) | set(proxies)) - {(r["case"],r["element_id"]) for r in records}:
        raise ValueError("review refers to missing source identities")
    groups = []
    for (case,root_id), members in sorted(pending.items()):
        a,_ = cases[case]
        by_id = {e["element_id"]:e for e in a["elements"]}
        parent_text = by_id[root_id]["text"]
        positions = {e["element_id"]:i for i,e in enumerate(a["elements"])}
        context = {e["element_id"]:{"before":[x["text"] for x in a["elements"][max(0,positions[e["element_id"]]-2):positions[e["element_id"]]]],
                                   "after":[x["text"] for x in a["elements"][positions[e["element_id"]]+1:positions[e["element_id"]]+3]]} for e in members}
        groups.append({"case":case, "parent_id":root_id, "parent_text":parent_text,
                       "regime_id":by_id[root_id]["features"]["hierarchy_regime_id"], "defect_type":"business_structure_unconfirmed",
                       "structure_hypothesis":"current automated tree is a hypothesis, not user confirmation",
                       "business_alternatives":["direct H2 peers", "retain business H3 peers with internal level placeholder"],
                       "element_ids":[e["element_id"] for e in members], "elements":members, "context":context,
                       "why_pending":"完整用户规则签名未覆盖，或实际映射不满足已确认规则；不得由树自洽自动关闭。"})
    count = Counter(r["evidence_origin"] for r in records)
    summary = {"declared_rule_count":len(rules), "user_confirmed_rule_count":len({p["rule_id"] for p in matched}),
               "matched_structure_count":len(matched), "business_structure_derived_count":count["business_structure_derived"],
               "strict_gt_count":sum(r["strict_element_gt"] for r in records), "flexible_gt_count":sum(r["flexible_element_gt"] for r in records),
               "strict_gt_passed":sum(r["strict_element_gt"] and r["gt_passed"] for r in records),
               "strict_gt_mismatch_count":sum(r["strict_element_gt"] and not r["gt_passed"] for r in records),
               "flexible_gt_mismatch_count":sum(r["flexible_element_gt"] and not r["gt_passed"] for r in records),
               "closed_previous_pending_count":sum((r["case"],r["element_id"]) in previous and r["passed"] for r in records),
               "business_pending_group_count":len(groups), "business_pending_element_count":sum(len(g["elements"]) for g in groups),
               "superseded_proposal_count":sum(r["proposal_status"] == "superseded" for r in records),
               "low_priority_proxy_pending_count":sum(r["evidence_origin"] == "proxy_review" and r["proxy_review_result"] == "pending"
                                                      and r["risk_level"] in {"P2", "SAMPLE"} for r in records),
               "rule_mapping_mismatch_count":sum(r["rule_expectation"] is not None and not r["rule_passed"] for r in records),
               "failed_confirmed_expectation_count":len(failures), "production_algorithm_modified":False}
    return {"summary":summary, "rules":rules, "matched_structures":matched, "elements":records,
            "pending":{"count":summary["business_pending_element_count"], "group_count":len(groups), "groups":groups}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cohort", "ground-truth", "rules", "previous", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--proxy-review", type=Path)
    args = parser.parse_args()
    try:
        result = reconcile(args.cohort, args.ground_truth, args.rules, args.previous, args.proxy_review)
    except (ValueError, KeyError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in (("business-review.json",result), ("pending-business-ground-truth.json",result["pending"])):
        (args.output / name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")
    lines = ["# 待确认业务结构问题", "", f"结构问题 {result['pending']['group_count']} 组，影响 {result['pending']['count']} 个元素。", ""]
    for group in result["pending"]["groups"]:
        lines += [f"## {group['case']} → {group['regime_id']} → {group['parent_text']}", "",group["why_pending"], "",
                  "当前结构推断与业务解释A/B分开；过期代理建议不作为当前结论。", "",
                  "| ID | 原文 | 原生H | effective H | 来源 | 当前selected |", "|---|---|---|---|---|---|"]
        lines += [f"| {e['element_id']} | {e['text'].replace('|','／')} | {e['source_native_heading_level']} | {e['effective_heading_level']} | {e['evidence_origin']} | {e['selected_decision']['role']} |" for e in group["elements"]]
        lines += ["", "受影响ID：" + ", ".join(group["element_ids"]), "", "关键上下文：" + json.dumps(group["context"],ensure_ascii=False), ""]
    (args.output / "pending-business-ground-truth.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps(result["summary"]))
    return 1 if result["summary"]["failed_confirmed_expectation_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
