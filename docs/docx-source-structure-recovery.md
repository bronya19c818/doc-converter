# DOCX 源结构恢复与验收边界

`docx_direct` 在既有标题资格和局部 Regime 之上恢复源结构。原生 Heading、编号文本和路径仍保留为源事实；恢复的族、路径、大纲与父关系单独记录。实现不读取业务 Ground Truth，也不依赖具体源 element_id。

## 恢复顺序

1. 在当前章、分节和附件边界内检查真实未编号短标题。真实实体必须先于它要挂载的直接数字主题，多个子主题及后续中文括号兄弟提供独立证据。
2. 真实子主题缺少数字前缀时，以紧随的多个相同根前缀条款作为内部索引。标题原文不补编号。
3. 没有可利用的真实父标题时，才考虑虚拟父节点。采用相同 qualification scope、初始根 Regime、编号族与样式的实体兄弟模板，或稳定原生 H3/H4 子树。H4 前缀必须匹配实际前序 H3 主题；当前分支的证据截至后续括号兄弟，模板独立核对。
4. 明确括号父与至少两个稳定数字兄弟可纠正孤立的源大纲偏离；更深的嵌套数字主题不得被拉平成兄弟。
5. 多个更深源大纲条目与后续更浅同编号主题冲突时，明确保留原样，不把唯一期望设为某个标题层。

确实未使用的 Schema 层继续压缩；原生前言不为独立编号体系垫层。无编号原生容器中的数字子体系保留实际父偏移，并通过祖先数字路径退出局部作用域。支持有效 H6，超过 H6 保留。

## 审计契约

每个真实元素记录 `source_defect_type`、`source_defect_resolution`、`parent_resolution_type`、`inferred_parent_id`、`effective_parent_id`、`source_native_heading_level`、`effective_heading_level`、`hierarchy_confidence` 与 `hierarchy_evidence`。置信度是启发式证据强度，不是概率。

`virtual_heading_nodes` 独立于真实 `heading_tree`；虚拟节点有 `virtual_node_id`、`expected_level`、真实根 `parent_id`、真实 `child_element_ids`、Regime、原因、置信度和证据 ID，没有真实 `element_id` 或编造的标题文本。真实节点的 `parent_id` 或 `children` 可以引用虚拟 ID；遍历时合并两个索引。虚拟节点不进入 Word 段落或样式映射。

`compressed_levels` 描述局部编号模型。`effective_level_variants` 汇总真实节点的有效层；同族存在多个有效层时，单值 `effective_levels` 为 null，避免把局部差异报告成全局常量。

`resolved` 指结构层与选定映射一致；只有显式编号冲突保留才是 `resolved_conservatively`。其他未知、超限或无法映射的源缺陷为 `unresolved`。分类后的审计不改变 selector 或 Word。实际完成映射还必须核对报告的 `xml_patch.modified_element_ids`，不能只看选定角色。

## 真实 Ground Truth

当前本地数据集由用户明确确认的 42 条 H3/H4/H6 和 2 条错误编号允许结果组成。范围只取上一轮 pending 中列出的标题，不扩散到区间正文。没有明确父 ID 的记录保持 null；只有明确父名称且源中唯一匹配时才绑定 ID。两条错误编号允许保留，或在充分独立证据下映射 H2，单独计数。

数据集、源文件及私有转换工件留在 `artifacts/source-structure-gt/` 和本地验收目录，不进入 Git。`DOCX_SOURCE_GT` 指向本地数据集时，`tests/test_docx_source_structure.py` 对三个完整真实源运行 API 转换，核对 SHA、ID、原文、角色、动作、确认父关系和实际 XML 修改。公共 CI 没有私有源，明确跳过这一项；本地执行结果是最终真实 GT 证据。

其他重复结构和旧代理建议可以进行独立源上下文复核，但不得标为 `user_confirmed`。审核按文档、Regime、父、缺陷与结构签名分组，并保留逐条记录。推断树自洽、HIGH 为零和 CI 成功都不能单独证明全篇语义正确。

## 保护与验证

恢复只改变分类证据与内部章节树，冻结 selector、转换策略、OOXML patch、样式模板、字体行距、页面分页及 Markdown/DOC 路径。`classifier.py` 只增加选定决策之后的审计收尾调用。

端到端案例覆盖实体父和首子同时缺编号、虚拟父充分/不足证据、分节/附件/独立数字体系隔离、前缀不匹配、晚到或嵌套父候选、错误大纲/编号、正常缺层、H6/超限及审计状态。新增行为先观察失败再修复。最终验证沿用 11 份真实源、90 条依据清单、44 条历史保留、31 条原标注及 6 个作者/公式反例，核对源 SHA、可见文本顺序、ZIP 与对象保护，并抽查实际 PDF 代表页。
