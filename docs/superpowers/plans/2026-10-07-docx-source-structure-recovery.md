# 源文档结构缺陷容错执行记录

起点c613e37，experiment/docx-direct-normalizer。用户提供明确源案例H3/H4/H6与两条错误编号的允许结果；保留.codegraph及既有本地资料，不创建另一实现任务或改main。

- [x] 固化用户GT：明确ID全纳入；技术规范范围只与原pending标题交集；父节点不明确为null；错误编号不把H2设为唯一预期。
- [x] 真实GT基线及源缺陷DOCX/API反例先RED（真实实体父、证据充分/不足虚拟父、错误源大纲/编号、正常缺层、H6/超限、边界隔离）。
- [x] source_structure_recovery独立模块：源事实/独立证据与结构假设分开；真实父优先，虚拟节点不具真实element_id、不写Word。
- [x] 支持regime祖先编号返回、实体编号丢失、稳定局部大纲校正与受约束虚拟父；记录结果/置信/证据。
- [x] 全部GT逐条验证、44历史保留重新分类、90依据清单回归；按文档/体系/父/缺陷分组审核。
- [x] 同11真源、6已知反例、31原GT/压力、全量检查、一次整体审查及修复。
- [ ] 独立提交、最终HEAD CI/main冲突、分级阻塞与merge-readiness。

Pre-flight: GT→API/导出验证使用相同source SHA/ID/文本；生产代码不读取本地GT、不含源ID特判。恢复输出→层级证据→既有selector→策略/mapper，冻结selector/policy/OOXML/字体页面/Markdown/DOC。

Ruling: 用户最新设计已提供边界、输出与TDD场景，直接执行；沿用现有干净实验checkout和简洁记录，不额外生成SDD实现/每任务评审流程。代价：最终统一审查保障新父链边界。

Ruling: ranges只取上一轮pending中的真实标题，不扩散到区间正文；重复源结构是新代理验证对象，不从文字等同自动产生user_confirmed。江西八个H6及上安p-0152可能已映射，仍纳入用户真GT验证，不假称新增修复。

Ruling: 两个错误编号只保存允许preserved或有充分独立结构证据的heading-2/mapped，单独计数，不纳入必须mapped的唯一角色GT分母。用户未确认父ID时保持null。

Ruling: classifier.py仅在既有selector完成后调用finish_source_audit，补充真实选定结果审计；不修改selector/策略/mapper/OOXML。源facts与恢复的family/path/outline明确分开。

Evidence: 本地不可变GT为42严格+2允许结果，基线为9正确、7错误映射、26保留；8条H6原已正确，不冒称新增修复。初次14条失败及后续作用域、原生前言、晚到父、有效层变体反例均先RED。修复后的新增DOCX/API场景23条全部通过，含全部真实GT实际XML修改验证。

Review: 一次整体code-reviewer与python-reviewer审查。嵌套短父回借和无关数字前缀两项先用2条E2E复现失败；候选父必须先于直接数字主题，H4必须属于实际前序H3数字根，当前分支截至括号兄弟，匹配模板另行验证。未知H7保留误计“保守解决”先用1条E2E复现失败；仅显式编号冲突保留计resolved_conservatively。大纲纠正、错误序列保留已提取私有函数；不添加新类型或框架。

Ruling: 源原生3/4模板可以存在于同一界限内其他显式括号节，但当前缺失分支的子证据不能借用该括号节；更深的嵌套数字段落不关闭外层H3所有者。所有模板依赖qualification scope和初始根Regime，禁止跨独立数字重置。

Verification: 最终稳定代码全量与11源复跑写入artifacts/source-structure-final-reviewed；此前迭代结果保留在各自目录，不能冒充最终代码验收。前端26测试/构建已通过且相关代码冻结；最终HEAD CI另行验证。未请求合并main。

Final local evidence: 后端249通过；Ruff/Mypy通过；11源12192元素结构保护通过；31原标注/压力与6作者公式通过；42严格GT均正确且实际修改，2错误编号均按允许结果保留；44历史保留均映射（部分预期仍为代理来源），90依据无误升。57 Regime、24实体恢复、2虚拟父、41带理论缺层压缩模型、13源大纲压缩节点；树跳跃及父子倒置均0。89个未获用户确认的案例合并为24组，其中46继承上一轮未决、43来自当前P1代理建议/缺实体判断，不能把它们计成新的真人GT；低优先级SAMPLE75另列。公开实现与测试提交，私有源/GT/审核工件不提交。
