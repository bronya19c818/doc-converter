"""DOCX/API cases for defective source trees, specified before recovery code.

Failure modes: an existing parent is replaced by fiction; source outline gaps
are mistaken for unused schema layers; numbering errors contaminate a schema;
weak/cross-boundary patterns manufacture parents; scope return strands a real
numbered peer; valid H6 is rejected; virtual nodes leak into Word or real IDs;
confirmed mapped GT is incorrectly counted as passing when merely preserved.
"""
import json
import os
from collections import Counter
from hashlib import sha256
from pathlib import Path

import pytest
from test_docx_local_structure import _convert

from scripts.verify_docx_selected import verify_sample


def _tree(actual):
    return actual["_analysis"]["document_baselines"]


def _mapped(actual, expected):
    for text, level in expected.items():
        assert actual[text]["selected_decision"]["role"] == f"heading-{level}"
        assert actual[text]["selected_decision"]["action"] == "mapped"


def test_existing_heading_without_numbering_is_the_real_parent(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("三、项目服务要求", None), ("支持内容", None),
        ("1. 入库辅助", None), ("这里是入库辅助的正文。", None),
        ("2. 在库辅助", None), ("这里是在库辅助的正文。", None),
        ("（二）执行要求", None), ("这里是执行要求的正文。", None),
    ])
    _mapped(actual, {"三、项目服务要求": 1, "支持内容": 2, "1. 入库辅助": 3, "2. 在库辅助": 3})
    parent = actual["支持内容"]
    assert parent["features"]["source_defect_type"] == "missing_numbering_on_existing_heading"
    for text in ("1. 入库辅助", "2. 在库辅助"):
        f = actual[text]["features"]
        assert f["effective_parent_id"] == parent["element_id"]
        assert f["parent_resolution_type"] == "existing_unnumbered_parent"
    assert _tree(actual)["virtual_heading_nodes"] == []


def test_missing_numeric_prefix_on_existing_heading_is_recovered_without_text_changes(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("三、服务要求", None), ("业务范围", None),
        ("1. 入库辅助", None), ("这里是入库辅助的正文。", None),
        ("在库辅助", None), ("2.1 仓位整理", None), ("这里是仓位整理的正文。", None),
        ("2.2 物资保管", None), ("这里是物资保管的正文。", None),
        ("安全辅助", None), ("4.1 安全责任", None), ("这里是安全责任的正文。", None),
        ("4.2 消防工作", None), ("这里是消防工作的正文。", None),
        ("5. 应急辅助", None), ("这里是应急辅助的正文。", None),
        ("（二）服务标准", None), ("这里是服务标准的正文。", None),
    ])
    _mapped(actual, {"业务范围": 2, "在库辅助": 3, "安全辅助": 3,
                     "2.1 仓位整理": 4, "2.2 物资保管": 4, "4.1 安全责任": 4, "4.2 消防工作": 4})
    for text, parent in (("2.1 仓位整理", "在库辅助"), ("4.1 安全责任", "安全辅助")):
        assert actual[text]["features"]["effective_parent_id"] == actual[parent]["element_id"]
        assert actual[parent]["features"]["numbering_family"] is None
    assert _tree(actual)["virtual_heading_nodes"] == []


def test_existing_parent_and_first_child_both_missing_numbering_are_recovered(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("三、项目要求", None), ("支持范围", None), ("入库辅助", None),
        ("1.1 辅助完成物资实物核对。", None), ("1.2 辅助完成出入库记录。", None),
        ("在库辅助", None), ("2.1 仓位整理", None), ("这里是仓位整理的正文。", None),
        ("2.2 物资保管", None), ("这里是物资保管的正文。", None),
        ("5. 应急辅助", None), ("这里是应急辅助的正文。", None),
        ("6. 资料归档", None), ("这里是资料归档的正文。", None),
        ("（二）服务标准", None), ("这里是服务标准的正文。", None),
    ])
    _mapped(actual, {"支持范围": 2, "入库辅助": 3, "在库辅助": 3, "2.1 仓位整理": 4, "2.2 物资保管": 4})
    assert actual["在库辅助"]["features"]["effective_parent_id"] == actual["支持范围"]["element_id"]
    assert _tree(actual)["virtual_heading_nodes"] == []


def test_later_unnumbered_content_cannot_be_reused_as_an_earlier_missing_parent(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("三、项目要求", None), ("1. 先行内容", None),
        ("1.1 这是先行事项的正文。", None), ("1.2 这是先行记录的正文。", None),
        ("2. 先行质量", None), ("这里是先行质量的正文。", None),
        ("（二）服务标准", None), ("这里是服务标准的正文。", None),
        ("过渡说明", None), ("入库辅助", None),
        ("1.1 这是后续核对的正文。", None), ("1.2 这是后续记录的正文。", None),
    ])
    e = actual["过渡说明"]
    assert not (e["selected_decision"]["role"].startswith("heading-") and e["selected_decision"]["action"] == "mapped")
    assert e["features"]["recovered_heading_family"] is None


def test_nested_unnumbered_topic_cannot_parent_earlier_direct_roots(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("一、作业要求", 1), ("7. 已有主题", 3), ("这里是已有主题的正文。", None),
        ("局部说明", None), ("局部步骤", None),
        ("1.1 这是局部记录的正文。", None), ("1.2 这是局部核对的正文。", None),
        ("8. 另一个主题", 3), ("这里是另一个主题的正文。", None),
        ("（二）安全要求", 2), ("这里是安全要求的正文。", None),
    ])
    assert actual["局部说明"]["features"]["recovered_heading_family"] is None
    for text in ("7. 已有主题", "8. 另一个主题"):
        assert actual[text]["features"]["effective_parent_id"] != actual["局部说明"]["element_id"]


def test_unrelated_decimal_owners_cannot_support_a_virtual_parent(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("七、设备规程", 1), ("7. 安全主题", 3), ("这里是安全主题的正文。", None),
        ("8. 台账主题", 3), ("这里是台账主题的正文。", None),
        ("1.1 无关前缀主题", 4), ("这里是无关前缀主题的正文。", None),
        ("2.1 另一无关前缀", 4), ("这里是另一无关前缀的正文。", None),
    ])
    assert _tree(actual)["virtual_heading_nodes"] == []


def test_repeated_structure_supports_a_virtual_parent_when_entity_is_absent(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("一、先行要求", 1), ("（一）实施范围", 2),
        ("1. 初装辅助", 3), ("这里是初装辅助的正文。", None),
        ("2. 维护辅助", 3), ("这里是维护辅助的正文。", None),
        ("（二）安全要求", 2), ("这里是安全要求的正文。", None),
        ("二、后续要求", 1),
        ("1. 后续入库", 3), ("这里是后续入库的正文。", None),
        ("2. 后续在库", 3), ("这里是后续在库的正文。", None),
        ("（二）后续安全", 2), ("这里是后续安全的正文。", None),
    ])
    _mapped(actual, {"1. 后续入库": 3, "2. 后续在库": 3})
    virtual = _tree(actual)["virtual_heading_nodes"]
    assert len(virtual) == 1
    node = virtual[0]
    assert node["expected_level"] == 2
    assert node["parent_id"] == actual["二、后续要求"]["element_id"]
    assert "element_id" not in node and "text" not in node
    assert set(node["child_element_ids"]) == {actual[t]["element_id"] for t in ("1. 后续入库", "2. 后续在库")}
    assert node["reason"] and node["confidence"]
    for text in ("1. 后续入库", "2. 后续在库"):
        assert actual[text]["features"]["parent_resolution_type"] == "inferred_virtual_parent"


def test_insufficient_parent_evidence_remains_preserved(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("一、先行要求", 1), ("（一）先行范围", 2),
        ("1. 先行内容", 3), ("这里是先行内容的正文。", None),
        ("二、后续要求", 1), ("1. 孤立内容", None), ("这里是孤立内容的正文。", None),
    ])
    assert actual["1. 孤立内容"]["selected_decision"]["action"] == "preserved"
    assert _tree(actual)["virtual_heading_nodes"] == []


@pytest.mark.parametrize("boundary", ["attachment", "section"])
def test_parent_pattern_cannot_cross_an_explicit_regime_boundary(boundary, tmp_path, monkeypatch):
    paragraphs = [("一、原要求", 1), ("（一）原范围", 2),
                  ("1. 原入库", 3), ("这里是原入库的正文。", None),
                  ("2. 原在库", 3), ("这里是原在库的正文。", None)]
    paragraphs.append(("附件A", None) if boundary == "attachment" else ("", 0))
    paragraphs.extend([("一、附属要求", None), ("1. 附属入库", None), ("这里是附属入库的正文。", None),
                       ("2. 附属在库", None), ("这里是附属在库的正文。", None)])
    actual = _convert(tmp_path, monkeypatch, paragraphs)
    _mapped(actual, {"一、附属要求": 1, "1. 附属入库": 2, "2. 附属在库": 2})
    assert _tree(actual)["virtual_heading_nodes"] == []


def test_parent_template_cannot_cross_an_independent_decimal_regime_reset(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("一、先行要求", 1), ("（一）先行范围", 2),
        ("1. 先行入库", 3), ("这里是先行入库的正文。", None),
        ("2. 先行在库", 3), ("这里是先行在库的正文。", None),
        ("1 技术范围", None), ("1.1 基本参数", 2), ("这里是基本参数的正文。", None),
        ("二、后续要求", 1), ("1. 后续入库", 3), ("这里是后续入库的正文。", None),
        ("2. 后续在库", 3), ("这里是后续在库的正文。", None),
        ("（二）后续标准", 2), ("这里是后续标准的正文。", None),
    ])
    assert actual["1. 后续入库"]["selected_decision"]["action"] == "preserved"
    assert actual["2. 后续在库"]["selected_decision"]["action"] == "preserved"
    assert _tree(actual)["virtual_heading_nodes"] == []


def test_wrong_native_outline_uses_the_proven_peer_parent_structure(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("一、业务规程", 1), ("（一）入库管理", 2),
        ("7. 工作检查", 3), ("这里是工作检查的正文。", None),
        ("8. 单据核对", 3), ("这里是单据核对的正文。", None),
        ("9. 业务清单", 2), ("这里是业务清单的正文。", None),
    ])
    _mapped(actual, {"7. 工作检查": 3, "8. 单据核对": 3, "9. 业务清单": 3})
    f = actual["9. 业务清单"]["features"]
    assert f["source_native_heading_level"] == 2
    assert f["source_defect_type"] == "incorrect_source_outline"
    assert f["effective_parent_id"] == actual["（一）入库管理"]["element_id"]


def test_outline_peer_recovery_does_not_flatten_a_nested_numbering_series(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("一、业务规程", 1), ("（一）入库管理", 2),
        ("7. 作业检查", 3), ("这里是作业检查的正文。", None),
        ("8. 作业管理", 3), ("1. 作业条件", 4), ("这里是作业条件的正文。", None),
        ("2. 实施流程", 4), ("这里是实施流程的正文。", None),
        ("9. 业务清单", 2), ("这里是业务清单的正文。", None),
    ])
    _mapped(actual, {"1. 作业条件": 4, "2. 实施流程": 4, "9. 业务清单": 3})
    for text in ("1. 作业条件", "2. 实施流程"):
        assert actual[text]["features"]["effective_parent_id"] == actual["8. 作业管理"]["element_id"]


def test_stable_native_subtrees_support_the_missing_source_layer(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("七、设备规程", 1), ("7. 安全管理", 3), ("这里是安全管理的正文。", None),
        ("8. 台账管理", 3), ("8.1 建立台账", 4), ("这里是建立台账的正文。", None),
        ("8.2 核验台账", 4), ("这里是核验台账的正文。", None),
        ("11. 编码管理", 3), ("11.1 存储编码", 4), ("这里是存储编码的正文。", None),
        ("11.2 仓位编码", 4), ("这里是仓位编码的正文。", None),
    ])
    _mapped(actual, {"8. 台账管理": 3, "8.1 建立台账": 4, "8.2 核验台账": 4,
                     "11. 编码管理": 3, "11.1 存储编码": 4, "11.2 仓位编码": 4})
    assert len(_tree(actual)["virtual_heading_nodes"]) == 1
    assert _tree(actual)["virtual_heading_nodes"][0]["expected_level"] == 2


def test_effective_family_audit_reports_local_variants_instead_of_a_false_global_level(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("一、正常要求", 1), ("1. 正常内容", None), ("这里是正常内容的正文。", None),
        ("2. 正常质量", None), ("这里是正常质量的正文。", None),
        ("二、设备规程", 1), ("8. 台账主题", 3),
        ("8.1 建立台账", 4), ("这里是建立台账的正文。", None),
        ("8.2 核验台账", 4), ("这里是核验台账的正文。", None),
        ("11. 编码主题", 3), ("11.1 编码规则", 4), ("这里是编码规则的正文。", None),
    ])
    _mapped(actual, {"1. 正常内容": 2, "2. 正常质量": 2, "8. 台账主题": 3, "11. 编码主题": 3})
    regime_id = actual["8. 台账主题"]["features"]["hierarchy_regime_id"]
    regime = next(r for r in _tree(actual)["hierarchy_regimes"] if r["regime_id"] == regime_id)
    assert regime["effective_levels"]["ARABIC_ENUM"] is None
    assert regime["effective_level_variants"]["ARABIC_ENUM"] == [2, 3]


def test_broken_numbering_never_uses_the_wrong_native_depth_as_truth(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("资料主体", 1), ("6. 技术文件", 2),
        ("1. 总体方案", 3), ("这里是总体方案的正文。", None),
        ("2. 实施安排", 3), ("这里是实施安排的正文。", None),
        ("5. 安全方案", 3), ("5.1 安全制度", 4), ("这里是安全制度的正文。", None),
        ("6. 风险方案", 4), ("这里是风险方案的正文。", None),
        ("7. 保密方案", 4), ("这里是保密方案的正文。", None),
        ("7. 技术服务", 2), ("这里是技术服务的正文。", None),
    ])
    for text in ("6. 风险方案", "7. 保密方案"):
        assert actual[text]["selected_decision"]["action"] == "preserved"
        assert actual[text]["features"]["source_defect_type"] == "broken_numbering_sequence"
        assert actual[text]["features"]["source_defect_resolution"] == "resolved_conservatively"


def test_normal_unused_schema_layer_still_compresses(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("一、总体要求", None), ("1. 服务内容", None), ("这里是服务内容的正文。", None),
        ("2. 服务质量", None), ("这里是服务质量的正文。", None),
    ])
    _mapped(actual, {"一、总体要求": 1, "1. 服务内容": 2, "2. 服务质量": 2})
    assert _tree(actual)["virtual_heading_nodes"] == []


def test_preserved_unsupported_descendant_is_not_a_resolved_source_defect(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("三、项目要求", None), ("支持范围", None),
        ("1. 入库主题", None), ("1.1 入库分项", None),
        ("1.1.1 核对事项", None), ("1.1.1.1 核对步骤", None),
        ("1.1.1.1.1 超限步骤", None), ("这里是超限步骤的正文。", None),
        ("2. 在库主题", None), ("这里是在库主题的正文。", None),
        ("（二）安全要求", None), ("这里是安全要求的正文。", None),
    ])
    e = actual["1.1.1.1.1 超限步骤"]
    assert e["selected_decision"]["action"] == "preserved"
    assert e["features"]["source_defect_type"] == "missing_numbering_on_existing_heading"
    assert e["features"]["source_defect_resolution"] == "unresolved"


def test_native_prologue_does_not_pad_the_independent_numbered_schema(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("前言", 1), ("这里是前言的正文。", None),
        ("一、总体要求", 2), ("（一）具体要求", 3), ("这里是具体要求的正文。", None),
    ])
    _mapped(actual, {"前言": 1, "一、总体要求": 1, "（一）具体要求": 2})
    assert _tree(actual)["virtual_heading_nodes"] == []


def test_ancestor_numeric_path_closes_a_scope_with_an_unnumbered_native_parent(tmp_path, monkeypatch):
    actual = _convert(tmp_path, monkeypatch, [
        ("项目材料", 1), ("5. 支撑材料", 2), ("5.1 技术响应", 3),
        ("5.1.4 参数响应", 4), ("装置说明", 5),
        ("（一）第一装置", None), ("这里是第一装置的正文。", None),
        ("（二）第二装置", None), ("这里是第二装置的正文。", None),
        ("5.2 合同业绩", None), ("5.2.1 业绩说明", 4), ("这里是业绩说明的正文。", None),
    ])
    _mapped(actual, {"（一）第一装置": 6, "（二）第二装置": 6,
                     "5.2 合同业绩": 3, "5.2.1 业绩说明": 4})
    assert actual["5.2 合同业绩"]["features"]["effective_parent_id"] == actual["5. 支撑材料"]["element_id"]


@pytest.mark.parametrize("extra", [False, True])
def test_valid_six_levels_are_supported_and_seven_remains_safe(extra, tmp_path, monkeypatch):
    paragraphs = [("总体材料", 1), ("5. 支撑材料", 2), ("5.1 技术响应", 3),
                  ("5.1.1 参数说明", 4), ("真实组件主题", 5),
                  ("（一）组件参数", None), ("这里是组件参数的正文。", None)]
    if extra:
        paragraphs += [("说明", 6), ("这里是深层说明的正文。", None)]
    actual = _convert(tmp_path, monkeypatch, paragraphs)
    _mapped(actual, {"（一）组件参数": 6})
    assert _tree(actual)["virtual_heading_nodes"] == []
    if extra:
        assert actual["说明"]["selected_decision"]["action"] == "preserved"


@pytest.mark.skipif(not os.environ.get("DOCX_SOURCE_GT"), reason="真实源和用户GT保持本地；设置DOCX_SOURCE_GT运行")
def test_user_confirmed_real_source_gt_through_api(tmp_path, monkeypatch):
    dataset = json.loads(Path(os.environ["DOCX_SOURCE_GT"]).read_text(encoding="utf-8"))
    monkeypatch.setenv("DOC_CONVERTER_LIBREOFFICE", str(tmp_path / "no-preview"))
    rows = dataset["elements"]
    assert len({(e["source_case"], e["element_id"]) for e in rows}) == len(rows) == 44
    results = []
    for case in sorted({e["source_case"] for e in rows}):
        labels = [e for e in rows if e["source_case"] == case]
        source = Path(labels[0]["source"])
        assert sha256(source.read_bytes()).hexdigest() == labels[0]["source_sha256"]
        assert all(e["evidence_origin"] == "user_confirmed" and e["source_sha256"] == labels[0]["source_sha256"] for e in labels)
        out = tmp_path / case
        verify_sample(source, out, [])
        a = json.loads((out / "docx-analysis.json").read_text(encoding="utf-8"))
        report = json.loads((out / "docx-normalization-report.json").read_text(encoding="utf-8"))
        assert a["source_sha256"] == labels[0]["source_sha256"]
        by_id = {e["element_id"]: e for e in a["elements"]}
        for label in labels:
            e = by_id[label["element_id"]]
            assert e["text"] == label["text"]
            d = e["selected_decision"]
            if label["review_status"] == "confirmed":
                passed = (d["role"], d["action"]) == (label["expected_role"], label["expected_action"])
                if passed:
                    passed &= e["element_id"] in report["xml_patch"]["modified_element_ids"]
                if label["parent_element_id"] is not None:
                    passed &= e["features"].get("effective_parent_id", e["features"].get("parent_heading_id")) == label["parent_element_id"]
            else:
                passed = d["action"] == "preserved" or (d["role"], d["action"]) == ("heading-2", "mapped") \
                    and bool(e["features"].get("hierarchy_evidence"))
            results.append({**label, "actual": d, "features": e["features"], "passed": passed,
                            "result": "correct" if passed else "preserved" if d["action"] != "mapped" else "incorrect"})
    counts = dict(Counter(e["result"] for e in results if e["review_status"] == "confirmed"))
    (tmp_path / "user-confirmed-gt-results.json").write_text(json.dumps({"counts": counts, "elements": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    assert all(e["passed"] for e in results), {"fixed": counts, "failures": [(e["source_case"], e["element_id"], e["actual"]["role"], e["actual"]["action"]) for e in results if not e["passed"]]}
