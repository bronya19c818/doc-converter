"""Actual DOCX/API artifacts → offline business-review CLI, specified first.

Failure modes: text-only approval; foreign regime/parent/prefix/topic matches;
copying selected as truth; nine chapter approved through the seven rule; old
H2 proposals remain active; strict element GT silently expands; source/audit
fingerprints mismatch; mapped labels close review without XML execution.
"""
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from test_docx_local_structure import _convert

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/reconcile_docx_business_review.py"
TOPICS = ["入库辅助", "在库辅助", "配送辅助", "安全辅助", "应急辅助", "资料归档", "其他事项"]


def _service(root="三、项目服务要求", *, defect=None):
    paragraphs = [(root, None), ("服务内容", None)]
    for n, title in enumerate(TOPICS, 1):
        paragraphs.append((f"{n}. {title}" if n != 3 else title, None))
        if n == 1 or n == 3:
            paragraphs += [(f"{n}.1 这是完整作业的说明正文。", None),
                           (f"{n}.2 这是完整记录的说明正文。", None)]
        elif n in {2, 4}:
            for child in range(1, 3 if n == 2 else 8):
                prefix = 9 if defect == "prefix" and n == 2 else n
                paragraphs += [(f"{prefix}.{child} {title}分项{child}", None),
                               ("这里是该分项的完整业务正文。", None)]
        else:
            paragraphs.append(("这里是主题的完整业务正文。", None))
    paragraphs += [("（二）服务要求", None), ("这里是服务要求的完整业务正文。", None)]
    if defect == "regime":
        paragraphs.insert(2, ("", 0))
    if defect == "topic":
        paragraphs = [(t.replace("配送辅助", "其他配送说明"), h) for t,h in paragraphs]
    return paragraphs


def _rules(source_hash, case, reference):
    evidence = {"evidence_origin": "user_confirmed_rule", "confirmation_reference": str(reference),
                "confirmation_sha256": sha256(b"fixture user rule").hexdigest()}
    return {"rules": [
        {**evidence, "rule_id": "service-rule", "kind": "service_content", "source_case": case,
         "source_sha256": source_hash, "parent_text": "三、项目服务要求", "entity_text": "服务内容",
         "topics": [{"ordinal": i, "title": title} for i,title in enumerate(TOPICS, 1)],
         "heading_clause_series": {"2": [1,2], "4": list(range(1,8))},
         "body_prefixes": [1,3], "next_sibling_text": "（二）服务要求"},
        {**evidence, "rule_id": "facilities-rule", "kind": "confirmed_child_peers", "source_case": case,
         "source_sha256": source_hash, "parent_text": "七、设施设备管理规程",
         "peer_ordinals": list(range(1,9)), "anchor_prefix": 8, "anchor_children": [1,2,3]},
    ]}


def _files(tmp_path, actual, *, peers=False, confirm_system=False):
    case = "real-original/fixture"
    cohort = tmp_path / "cohort"
    folder = cohort / case
    folder.mkdir(parents=True)
    a = actual["_analysis"]
    reference = tmp_path / "fixture-user-rule.md"
    reference.write_bytes(b"fixture user rule")
    for name in ("docx-analysis.json", "docx-normalization-report.json"):
        (folder / name).write_bytes((tmp_path / "api" / name).read_bytes())
    summary = {"results": [{"case": "fixture", "source": str(tmp_path / "source.docx"),
                            "source_sha256": a["source_sha256"], "passed": True, "source_unchanged": True}]}
    (cohort / "real-original/summary.json").write_text(json.dumps(summary), encoding="utf-8")
    pending = []
    gt = []
    current_root = None
    for e in a["elements"]:
        f = e["features"]
        if f["numbering_family"] == "CN_ENUM":
            current_root = e["text"]
        system_anchor = confirm_system and e["text"].startswith(("11.1", "11.2", "11.3", "11.4"))
        if e["text"].startswith(("8.1", "8.2", "8.3")) or system_anchor:
            gt.append({"source_case": case, "source_sha256": a["source_sha256"], "element_id": e["element_id"],
                       "text": e["text"], "expected_role": "heading-4", "expected_action": "mapped",
                       "parent_element_id": None if system_anchor else actual["8. 台账管理"]["element_id"], "review_status": "confirmed",
                       "evidence_origin": "user_confirmed", "confirmation_reference": str(reference),
                       "confirmation_sha256": sha256(reference.read_bytes()).hexdigest()})
        service_member = current_root in {"三、项目服务要求", "四、其他要求"} and f["numbering_family"] != "CN_ENUM" and e["text"] != "（二）服务要求"
        peer_member = current_root in {"七、设施设备管理规程", "九、系统数据管理规程"} and f["numbering_family"] == "ARABIC_ENUM"
        if f["effective_heading_level"] and (service_member or peer_member):
            pending.append({"case": case, "source_sha256": a["source_sha256"], "element_id": e["element_id"],
                            "text": e["text"], "recommended_role": "heading-2" if peers and f["numbering_family"] == "ARABIC_ENUM" else None})
    truth_ids = {e["element_id"] for e in gt}
    pending = [e for e in pending if e["element_id"] not in truth_ids]
    sample = next(e for e in a["elements"] if e["text"].endswith("正文。"))
    proxy = {"case":case, "source_sha256":a["source_sha256"], "element_id":sample["element_id"],
             "text":sample["text"], "proxy_role":None, "risk_level":"SAMPLE", "result":"pending"}
    rules = _rules(a["source_sha256"], case, reference)
    if confirm_system:
        rules["rules"].append({**rules["rules"][1], "rule_id": "systems-rule", "parent_text": "九、系统数据管理规程",
                               "peer_ordinals": list(range(1,12)), "anchor_prefix": 11, "explicit_peer_level": 3,
                               "anchor_children": [1,2,3,4],
                               "business_explanation": "mixed numbering; business H3/H4 retained, no user-confirmed missing H2 entity"})
    for name, data in (("gt.json", {"elements": gt}), ("rules.json", rules),
                       ("proxy-review.json", {"elements":[proxy]}),
                       ("previous.json", {"groups": [{"elements": pending}]})):
        (tmp_path / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return cohort


def _run(tmp_path, cohort):
    result = subprocess.run([sys.executable, str(SCRIPT), "--cohort", str(cohort),
                             "--ground-truth", str(tmp_path / "gt.json"), "--rules", str(tmp_path / "rules.json"),
                             "--proxy-review", str(tmp_path / "proxy-review.json"),
                             "--previous", str(tmp_path / "previous.json"), "--output", str(tmp_path / "review")],
                            capture_output=True, text=True, encoding="utf-8", timeout=90)
    return result


@pytest.mark.parametrize("confirm_system", [False, True])
def test_business_rules_through_actual_docx_api_and_cli(confirm_system, tmp_path, monkeypatch):
    paragraphs = _service() + [("四、已有规程", 1), ("（一）已有主题", 2),
                              ("1. 原主题", 3), ("1.1 原分项", 4), ("这里是原分项的完整正文。", None)]
    paragraphs.append(("七、设施设备管理规程", 1))
    for i in range(1,9):
        paragraphs += [(f"{i}. 台账管理" if i == 8 else f"{i}. 设施主题{i}", 3),
                       ("这里是设施主题的完整正文。", None)]
    for child in range(1,4):
        paragraphs += [(f"8.{child} 台账分项{child}", 4), ("这里是台账分项的完整正文。", None)]
    paragraphs.append(("九、系统数据管理规程", 1))
    for i in range(1,12):
        paragraphs += [(f"{i}. 系统主题{i}", 3), ("这里是系统主题的完整正文。", None)]
    for child in range(1,5):
        paragraphs += [(f"11.{child} 编码分项{child}", 4), ("这里是编码分项的完整正文。", None)]
    actual = _convert(tmp_path, monkeypatch, paragraphs)
    cohort = _files(tmp_path, actual, peers=True, confirm_system=confirm_system)
    fingerprints = {p: sha256(p.read_bytes()).hexdigest() for p in [tmp_path / "gt.json", tmp_path / "source.docx",
                    *cohort.rglob("docx-*.json")]}
    result = _run(tmp_path, cohort)
    assert result.returncode == 0, result.stderr
    review = json.loads((tmp_path / "review/business-review.json").read_text(encoding="utf-8"))
    assert review["summary"]["user_confirmed_rule_count"] == (3 if confirm_system else 2)
    assert review["summary"]["business_structure_derived_count"] == (36 if confirm_system else 25)
    facilities = [e for e in review["elements"] if e.get("rule_id") == "facilities-rule"]
    assert len(facilities) == 8 and all(e["expected_role"] == "heading-3" for e in facilities)
    assert all(e["proposal_status"] == "superseded" for e in facilities)
    assert all(e["evidence_origin"] == "business_structure_derived" for e in facilities)
    pending = json.loads((tmp_path / "review/pending-business-ground-truth.json").read_text(encoding="utf-8"))
    if confirm_system:
        assert pending["group_count"] == 0
        proof = next(p for p in review["matched_structures"] if p["rule_id"] == "systems-rule")
        assert actual["11.4 编码分项4"]["element_id"] in proof["evidence_element_ids"]
    else:
        system = next(g for g in pending["groups"] if g["parent_text"] == "九、系统数据管理规程")
        assert len(system["element_ids"]) == 11
        assert len(system["business_alternatives"]) == 2
        assert all(e["business_expected_role"] is None for e in system["elements"])
    assert review["summary"]["strict_gt_count"] == (7 if confirm_system else 3)
    assert review["summary"]["low_priority_proxy_pending_count"] == 1
    assert any(e["evidence_origin"] == "proxy_review" and e["business_expected_role"] is None for e in review["elements"])
    assert all(sha256(p.read_bytes()).hexdigest() == h for p,h in fingerprints.items())
    first = (tmp_path / "review/business-review.json").read_bytes()
    assert _run(tmp_path, cohort).returncode == 0
    assert (tmp_path / "review/business-review.json").read_bytes() == first


@pytest.mark.parametrize("defect", ["parent", "regime", "prefix", "topic"])
def test_incomplete_source_signature_does_not_approve_identical_words(defect, tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, _service("四、其他要求" if defect == "parent" else "三、项目服务要求", defect=defect))
    cohort = _files(tmp_path, actual)
    result = _run(tmp_path, cohort)
    assert result.returncode == 0, result.stderr
    review = json.loads((tmp_path / "review/business-review.json").read_text(encoding="utf-8"))
    assert review["summary"]["business_structure_derived_count"] == 0
    assert review["summary"]["business_pending_element_count"] > 0


def test_audit_without_actual_xml_mapping_cannot_close_business_review(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, _service())
    cohort = _files(tmp_path, actual)
    report_path = cohort / "real-original/fixture/docx-normalization-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["xml_patch"]["modified_element_ids"].remove(actual["服务内容"]["element_id"])
    report_path.write_text(json.dumps(report), encoding="utf-8")
    result = _run(tmp_path, cohort)
    assert result.returncode == 1
    review = json.loads((tmp_path / "review/business-review.json").read_text(encoding="utf-8"))
    assert review["summary"]["rule_mapping_mismatch_count"] == 1


def test_foreign_source_fingerprint_is_rejected_before_review_writes(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, _service())
    cohort = _files(tmp_path, actual)
    rules = json.loads((tmp_path / "rules.json").read_text(encoding="utf-8"))
    rules["rules"][0]["source_sha256"] = "0" * 64
    (tmp_path / "rules.json").write_text(json.dumps(rules), encoding="utf-8")
    result = _run(tmp_path, cohort)
    assert result.returncode != 0
    assert "fingerprint" in result.stderr
    assert not (tmp_path / "review/business-review.json").exists()


@pytest.mark.parametrize("defect", ["hash", "missing", "changed"])
def test_unverifiable_user_confirmation_cannot_close_pending(defect, tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, _service())
    cohort = _files(tmp_path, actual)
    if defect == "hash":
        rules = json.loads((tmp_path / "rules.json").read_text(encoding="utf-8"))
        rules["rules"][0]["confirmation_sha256"] = "0" * 64
        (tmp_path / "rules.json").write_text(json.dumps(rules), encoding="utf-8")
    elif defect == "missing":
        (tmp_path / "fixture-user-rule.md").unlink()
    else:
        (tmp_path / "fixture-user-rule.md").write_bytes(b"new unconfirmed proposal")
    result = _run(tmp_path, cohort)
    assert result.returncode == 2
    assert "confirmation" in result.stderr
    assert not (tmp_path / "review/business-review.json").exists()


def test_proxy_record_cannot_be_promoted_to_strict_user_gt(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, _service())
    cohort = _files(tmp_path, actual)
    e = actual["服务内容"]
    truth = {"elements":[{"source_case":"real-original/fixture", "source_sha256":actual["_analysis"]["source_sha256"],
                          "element_id":e["element_id"], "text":e["text"], "expected_role":"heading-2",
                          "expected_action":"mapped", "parent_element_id":None,
                          "evidence_origin":"proxy_review", "review_status":"confirmed"}]}
    (tmp_path / "gt.json").write_text(json.dumps(truth),encoding="utf-8")
    result = _run(tmp_path, cohort)
    assert result.returncode == 2
    assert "GT" in result.stderr
    assert not (tmp_path / "review/business-review.json").exists()


@pytest.mark.parametrize("conflict", ["action", "parent"])
def test_conflicting_gt_and_rule_expectations_are_rejected(conflict, tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, _service())
    cohort = _files(tmp_path, actual)
    e = actual["服务内容"]
    reference = tmp_path / "fixture-user-rule.md"
    g = {"source_case":"real-original/fixture", "source_sha256":actual["_analysis"]["source_sha256"],
         "element_id":e["element_id"], "text":e["text"], "expected_role":"heading-2",
         "expected_action":"preserved" if conflict == "action" else "mapped",
         "parent_element_id":actual["1. 入库辅助"]["element_id"] if conflict == "parent" else None,
         "evidence_origin":"user_confirmed", "review_status":"confirmed",
         "confirmation_reference":str(reference), "confirmation_sha256":sha256(reference.read_bytes()).hexdigest()}
    (tmp_path / "gt.json").write_text(json.dumps({"elements":[g]}),encoding="utf-8")
    result = _run(tmp_path, cohort)
    assert result.returncode == 2
    assert "conflict" in result.stderr
    assert not (tmp_path / "review/business-review.json").exists()


@pytest.mark.parametrize("document", ["previous", "proxy-review"])
def test_duplicate_review_identities_cannot_be_silently_dropped(document, tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, _service())
    cohort = _files(tmp_path, actual)
    path = tmp_path / f"{document}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["groups"][0]["elements"] if document == "previous" else data["elements"]
    rows.append(rows[0].copy())
    path.write_text(json.dumps(data),encoding="utf-8")
    result = _run(tmp_path, cohort)
    assert result.returncode == 2
    assert "duplicate" in result.stderr
    assert not (tmp_path / "review/business-review.json").exists()


@pytest.mark.parametrize("outside", ["../escaped", "/absolute/case"])
def test_manifest_case_cannot_read_outside_its_cohort(outside, tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, _service())
    cohort = _files(tmp_path, actual)
    path = cohort / "real-original/summary.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["results"][0]["case"] = outside
    path.write_text(json.dumps(data),encoding="utf-8")
    result = _run(tmp_path, cohort)
    assert result.returncode == 2
    assert "case path" in result.stderr
    assert not (tmp_path / "review/business-review.json").exists()
