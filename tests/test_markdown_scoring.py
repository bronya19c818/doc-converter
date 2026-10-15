import pytest

from doc_converter.normalizer import normalize_markdown


def normalize(source: str):
    return normalize_markdown(source, filename="报告.md")


def test_auto_extracts_all_title_area_roles_without_confirmation():
    result = normalize("# 仓储管理实施方案\n\n——配送协同专项\n\n单位：测试电力公司\n\n部门：物资部\n\n作者：张三、李四\n\n日期：2026年10月14日\n\n摘要：规范仓储流程。\n\n关键词：仓储；配送\n\n一、实施背景\n\n正文。")
    assert result.metadata == {
        "title": "仓储管理实施方案", "subtitle": "——配送协同专项",
        "organization": "测试电力公司", "department": "物资部",
        "authors": ["张三", "李四"], "date": "2026年10月14日",
        "abstract": "规范仓储流程。", "keywords": ["仓储", "配送"],
    }
    assert "# 一、实施背景" in result.markdown
    decisions = result.report["decisions"]
    assert {d["role"] for d in decisions} >= {"document-title", "document-subtitle", "organization", "department", "author", "date", "abstract-label", "keywords-label", "heading-1", "body-paragraph"}
    assert all("candidates" in d and "margin" in d and "line" in d for d in decisions)


def test_full_document_numbering_keeps_parentheses_distinct():
    source = "# 方案\n\n一、背景\n\n（一）现状\n\n1. 项目情况\n\n（1）具体问题\n\n正文。\n\n（2）另一问题\n\n二、目标\n\n（二）工作措施\n\n2. 项目目标\n\n（3）落实步骤\n\n正文。"
    result = normalize(source)
    for text, level in [("一、背景", 1), ("（一）现状", 2), ("1. 项目情况", 3), ("（1）具体问题", 4), ("（2）另一问题", 4), ("二、目标", 1), ("2. 项目目标", 3), ("（3）落实步骤", 4)]:
        assert f"{'#' * level} {text}" in result.markdown


def test_explicit_hierarchy_and_front_matter_win():
    result = normalize("---\ntitle: 已有标题\norganization: 原有单位\n---\n\n## 背景\n\n### 一、措施\n\n#### （一）实施\n\n##### 1. 工作\n\n###### （1）步骤\n\n正文。")
    assert result.metadata["title"] == "已有标题"
    assert "# 背景" in result.markdown.splitlines()
    assert "## 一、措施" in result.markdown.splitlines()
    assert "##### （1）步骤" in result.markdown.splitlines()


def test_medium_score_with_full_document_evidence_is_applied():
    result = normalize("一、背景\n\n正文。\n\n二、目标\n\n正文。")
    assert "# 一、背景" in result.markdown
    d = next(d for d in result.report["decisions"] if d["before"] == "一、背景")
    assert d["action"] == "mapped"
    assert d["confidence_band"] == "medium"
    assert any(e["stage"] == "context" for c in d["candidates"] for e in c["evidence"])


@pytest.mark.parametrize("block", [
    "````markdown\n# 假标题\n```\n一、不是标题\n````",
    "    # 缩进代码\n    （一）不是标题",
    "- 列表\n  - 一、嵌套条目\n    延续文字\n- 条目二",
    "1. 完成检查。\n2. 开始配送。",
    "> # 引用标题\n> （一）引用内容",
    "| 字段 | 值 |\n| --- | --- |\n| 一、字段 | `代码` |",
    "[^note]: 一、脚注内容\n    续行",
])
def test_protected_blocks_keep_exact_source(block):
    result = normalize("# 实施方案\n\n一、背景\n\n正文含有 [链接](https://example.com/a) 和 ![图片](images/a.png)，以及 `一、代码`[^note]。\n\n" + block + "\n")
    assert block in result.markdown
    assert result.report["integrity"]["passed"]


def test_body_numbering_does_not_become_heading():
    source = "# 实施方案\n\n一、背景\n\n（1）按照物资需求开展配送，确保按期到达。\n\n1.1 需要根据需求组织车辆\n\n2. 实际金额为100元。"
    result = normalize(source)
    assert "# （1）" not in result.markdown
    assert "# 1.1" not in result.markdown
    assert "# 2. 实际" not in result.markdown


def test_metadata_inline_links_and_code_remain_renderable_content():
    result = normalize("# 实施方案\n\n摘要：保留 **重点**、[链接](https://example.com) 和 `代码`。\n\n关键词：仓储；配送\n\n一、背景\n\n正文。")
    assert result.metadata["abstract"] == "保留 **重点**、[链接](https://example.com) 和 `代码`。"
    assert result.report["integrity"]["passed"]


def test_unmarked_prose_is_not_guessed_as_document_title():
    result = normalize("今天我们讨论配送方案\n\n本段说明业务现状。")
    assert "title" not in result.metadata
    assert "今天我们讨论配送方案" in result.markdown


@pytest.mark.parametrize("ending", ["\n", "\n\n", "\n\n\n"])
def test_trailing_blank_lines_preserve_source_line_mapping(ending):
    result = normalize("# 方案\n\n一、背景\n\n正文。" + ending)
    assert next(d for d in result.report["decisions"] if d["before"] == "正文。")["line"] == 5


def test_front_matter_roles_have_explicit_evidence_in_audit():
    result = normalize("---\ntitle: 明确题名\norganization: 明确单位\ndepartment: 物资部\n---\n\n## 正文\n\n正文。")
    d = next(d for d in result.report['decisions'] if d['role'] == 'document-title')
    assert d['line'] == 2
    assert d['features']['front_matter'] is True
    assert d['target_style'] == 'DC_DocumentTitle'


def test_four_backtick_fence_keeps_toc_and_headers_literal():
    code = '````markdown\n```\n# 目次\nQ/GDW 1234—2024\nQ/GDW 1234—2024\n# 一、示例\n````'
    result = normalize('# 方案\n\n' + code + '\n\n一、背景\n\n正文。')
    assert code in result.markdown


def test_contiguous_title_metadata_lines_are_separate_fields():
    result = normalize('# 配送方案\n作者：张三\n单位：测试公司\n部门：物资部\n日期：2026年10月14日\n\n一、背景\n\n正文。')
    assert result.metadata['authors'] == ['张三']
    assert result.metadata['organization'] == '测试公司'
    assert result.metadata['department'] == '物资部'
    assert result.metadata['date'] == '2026年10月14日'


def test_standalone_abstract_label_keeps_content_and_following_metadata():
    result = normalize("# 方案\n\n摘要\n\n这是摘要正文。\n\n关键词：仓储；配送\n\n一、背景\n\n正文。")
    assert result.metadata["abstract"] == "这是摘要正文。"
    assert result.metadata["keywords"] == ["仓储", "配送"]
    assert result.markdown.count("这是摘要正文。") == 1


def test_reference_caption_and_table_roles_are_audited():
    result = normalize("# 方案\n\n一、背景\n\n表1 配送记录\n\n| 项目 | 数量 |\n| --- | --- |\n| A | 10 |\n\n图1 配送布局\n\n参考文献\n\n[1] 作者，研究报告，2026。\n\n## 附录\n\n附件正文。")
    assert {d["role"] for d in result.report["decisions"]} >= {"table-caption", "figure-caption", "body-table", "reference-heading", "reference-entry"}
    assert result.report["decisions"][-1]["role"] == "body-paragraph"


def test_decimal_explicit_anchor_is_relative_to_number_depth():
    result = normalize('---\ntitle: 方案\n---\n\n## 1. 范围\n\n### 1.1 基本范围\n\n1.1.1 具体范围\n\n1.1.1.1 深层范围')
    assert '#### 1.1.1 具体范围' in result.markdown
    assert '##### 1.1.1.1 深层范围' in result.markdown


def test_title_above_varied_numbered_headings_is_still_document_title():
    result = normalize('# 配送方案\n\n## 一、背景\n\n### （一）现状\n\n正文。')
    assert result.metadata['title'] == '配送方案'
    assert '# 一、背景' in result.markdown.splitlines()
    assert '## （一）现状' in result.markdown.splitlines()


def test_numbered_reference_heading_uses_reference_role():
    result = normalize('# 配送方案\n\n一、背景\n\n正文。\n\n二、参考文献\n\n[1] 研究报告，2026。')
    assert next(d for d in result.report['decisions'] if d['before'] == '二、参考文献')['role'] == 'reference-heading'


@pytest.mark.parametrize('block', ['    <table><tr><td>literal</td></tr></table>', '````markdown\n```\n<table><tr><td>literal</td></tr></table>\n````'])
def test_html_table_in_code_is_preserved(block):
    assert block in normalize('# 方案\n\n' + block).markdown


def test_standalone_abstract_without_blank_lines_is_extracted():
    result = normalize('# 方案\n\n摘要\n这是摘要正文。\n关键词：仓储；配送\n\n一、背景\n\n正文。')
    assert result.metadata['abstract'] == '这是摘要正文。'
    assert result.metadata['keywords'] == ['仓储', '配送']


def test_metadata_list_splitting_does_not_break_markdown_destinations():
    result = normalize('# 方案\n\n作者：[张三](https://example.com/a,b)、李四\n\n关键词：[仓储](https://example.com/a;b)；配送\n\n一、背景\n\n正文。')
    assert result.metadata['authors'] == ['[张三](https://example.com/a,b)', '李四']
    assert result.metadata['keywords'] == ['[仓储](https://example.com/a;b)', '配送']
    assert result.report['integrity']['passed']


def test_action_sentences_without_punctuation_remain_body():
    result = normalize('一、背景\n\n1.1 配送由本部门组织实施\n\n1.2 所有货物按照要求装箱\n\n二、目标\n\n正文。')
    assert '# 1.1' not in result.markdown
    assert '# 1.2' not in result.markdown


def test_annotated_long_and_boundary_corpus_meets_quality_floor():
    from scripts.verify_markdown_scoring import evaluate
    metrics = evaluate()['metrics']
    assert metrics['annotated_items'] == 230
    assert metrics['heading_items'] == 61
    assert metrics['role_accuracy'] >= .98
    assert metrics['heading_layer_accuracy'] >= .98
    assert metrics['correct_auto_coverage'] >= .98
