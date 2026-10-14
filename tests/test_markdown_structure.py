from doc_converter.normalizer import normalize_markdown


def result(source):
    return normalize_markdown(source, filename="复杂报告.md")


def roles(source):
    return {d["before"]: d for d in result(source).report["decisions"]}


def test_sparse_chinese_families_compress_and_share_tree():
    source = "# 仓储报告\n\n（一）入库管理\n\n1. 实物核对\n\n记录数量。\n\n2. 单据整理\n\n留存凭证。\n\n（二）在库管理\n\n登记结果。"
    d = roles(source)
    assert d["（一）入库管理"]["role"] == "heading-1"
    assert d["1. 实物核对"]["role"] == "heading-2"
    assert (
        d["1. 实物核对"]["features"]["effective_parent_id"]
        == d["（一）入库管理"]["features"]["element_id"]
    )


def test_shared_recovery_uses_existing_unnumbered_parent():
    d = roles(
        "三、服务要求\n\n支持内容\n\n1. 入库辅助\n\n核对实物。\n\n2. 在库辅助\n\n核对账目。\n\n（二）执行要求\n\n登记结果。"
    )
    assert d["支持内容"]["role"] == "heading-2"
    assert d["1. 入库辅助"]["role"] == "heading-3"
    assert (
        d["1. 入库辅助"]["features"]["effective_parent_id"]
        == d["支持内容"]["features"]["element_id"]
    )
    assert (
        d["支持内容"]["features"]["source_defect_type"] == "missing_numbering_on_existing_heading"
    )


def test_parallel_manual_sequence_is_body_despite_document_title():
    d = roles(
        "# 采购报告\n\n一、物资清单\n\n登记如下。\n\n（1）电缆\n\n（2）变压器\n\n（3）开关\n\n汇总数量。\n\n二、结果\n\n完成核对。"
    )
    for t in ["（1）电缆", "（2）变压器", "（3）开关"]:
        assert d[t]["role"] == "body-paragraph"
        assert (
            d[t]["features"]["manual_sequence_candidate"]
            or d[t]["features"]["manual_sequence_uncertain"]
        )


def test_long_heading_and_weak_action_word_do_not_block_recall():
    text = "一、关于完善多级仓储物资协同配送与退役物资全过程管理的实施要求及组织保障机制"
    d = roles(text + "\n\n明确岗位职责。\n\n二、需要统筹考虑的配送组织因素\n\n结合车型安排。")
    assert d[text]["role"] == "heading-1"
    assert d["二、需要统筹考虑的配送组织因素"]["role"] == "heading-1"


def test_organization_substrings_do_not_consume_body_heading():
    d = roles("# 仓储报告\n\n## 配送中心管理模式\n\n正文。\n\n## 公司预算管理现状\n\n正文。")
    assert d["## 配送中心管理模式"]["role"] == "heading-2"
    assert d["## 公司预算管理现状"]["role"] == "heading-2"
    assert "organization" not in result("# 仓储报告\n\n## 配送中心管理模式\n\n正文。").metadata


def test_appendix_restarts_numbering_and_ends_references():
    d = roles(
        "# 管理报告\n\n一、背景\n\n（一）范围\n\n正文。\n\n参考文献\n\n[1] 研究资料。\n\n附录A 核查标准\n\n1 范围\n\n1.1 核查对象\n\n正文。\n\n2 记录\n\n正文。"
    )
    assert d["附录A 核查标准"]["role"] == "heading-1"
    assert d["1 范围"]["role"] == "heading-2"
    assert d["1.1 核查对象"]["role"] == "heading-3"
    assert d["正文。"]["role"] == "body-paragraph"
    assert d["1 范围"]["features"]["region"] == "postface"


def test_normalization_is_idempotent_with_recovered_structure():
    source = "# 管理报告\n\n（一）入库\n\n1. 实物核对\n\n正文。\n\n（二）在库\n\n正文。"
    one = result(source)
    assert result(one.markdown).markdown == one.markdown


def test_raw_scores_remain_local_and_final_context_has_tree():
    source = "一、背景\n\n正文。\n\n二、目标\n\n正文。"
    r = result(source)
    d = r.report["decisions"][0]
    assert r.report["context"]["heading_tree"]
    assert d["features"]["hierarchy_regime_id"]
    assert any(c["raw_score"] != c["resolved_score"] for c in d["candidates"])


def test_bare_authors_are_not_joined_to_subtitle_by_import_cleanup():
    r = result(
        "# 仓储协同研究\n\n——基于配送需求的分析\n\n张三、李四\n\n示例研究院\n\n2026年10月14日\n\n一、背景\n\n正文。"
    )
    assert r.metadata["subtitle"] == "——基于配送需求的分析"
    assert r.metadata["authors"] == ["张三", "李四"]


def test_numbering_change_inside_chapter_keeps_actual_parent():
    d = roles(
        "第一章 业务要求\n\n一、入库\n\n正文。\n\n二、在库\n\n正文。\n\n1 范围\n\n1.1 核对对象\n\n正文。"
    )
    assert d["1 范围"]["role"] == "heading-3"
    assert d["1.1 核对对象"]["role"] == "heading-4"
    assert d["1 范围"]["features"]["effective_parent_id"] == d["二、在库"]["features"]["element_id"]


def test_appendix_keeps_chinese_children_below_boundary():
    d = roles(
        "一、背景\n\n正文。\n\n附录A 资料\n\n一、记录\n\n（一）数量\n\n正文。\n\n（二）金额\n\n正文。"
    )
    assert d["一、记录"]["role"] == "heading-2"
    assert d["（一）数量"]["role"] == "heading-3"


def test_confirmed_broken_sequence_is_preserved_and_audited():
    source = "# 资料主体\n\n## 6. 技术文件\n\n### 1. 总体方案\n\n正文。\n\n### 2. 实施安排\n\n正文。\n\n### 5. 安全方案\n\n#### 5.1 安全制度\n\n正文。\n\n#### 6. 风险方案\n\n正文。\n\n#### 7. 保密方案\n\n正文。\n\n## 7. 技术服务\n\n正文。"
    r = result(source)
    decisions = {d["before"]: d for d in r.report["decisions"]}
    for text in ["#### 6. 风险方案", "#### 7. 保密方案"]:
        d = decisions[text]
        assert d["role"] == "preserved"
        assert d["action"] == "preserved"
        assert d["features"]["source_defect_type"] == "broken_numbering_sequence"
        assert text in r.markdown


def test_mixed_appendix_source_levels_remain_idempotent_after_repair():
    source = "### 附录A 说明\n\n正文。\n\n（一）范围\n\n正文。\n\n## 1.1 说明\n\n正文。"
    first = result(source)
    assert result(first.markdown).markdown == first.markdown


def test_doc_export_escaped_numbering_does_not_merge_heading_with_body():
    source = "一、服务要求\n\n支持内容\n\n1\\. 入库辅助\n\n核对实物。\n\n2\\. 在库辅助\n\n核对账目。\n\n（二）执行要求\n\n登记结果。"
    r = result(source)
    d = {x["before"]: x for x in r.report["decisions"]}
    assert d["1\\. 入库辅助"]["role"] == "heading-3"
    assert d["核对实物。"]["role"] == "body-paragraph"
    assert d["支持内容"]["role"] == "heading-2"


def test_appendix_boundary_does_not_remove_previous_headings_child_evidence():
    source = "一、服务要求\n\n支持内容\n\n1\\. 入库辅助\n\n核对实物。\n\n2\\. 在库辅助\n\n核对账目。\n\n（二）执行要求\n\n登记结果。\n\n附录A 说明\n\n正文。"
    d = roles(source)
    assert d["支持内容"]["role"] == "heading-2"
    assert d["（二）执行要求"]["role"] == "heading-2"
