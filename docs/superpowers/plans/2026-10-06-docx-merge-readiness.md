# DOCX Direct 合并前收尾执行记录

范围以用户收尾计划为准：作者姓氏事实泛化、风险分级/去重/确定性抽样、11 份真实文档复验、独立审核记录与 HEAD 的 GitHub CI。不得改 selector、policy、OOXML patch、全局阈值、编号家族推断、样式、页面和 Markdown/DOC 路线。

起点：d154ef9，experiment/docx-direct-normalizer。既有 CI 未提交改动为创建 artifacts 目录，保留并验证；.codegraph/ 为既有未跟踪目录，保留。

- [ ] 先写 DOCX/API/CLI 端到端反例，观察失败
- [ ] 泛化作者 shape/surname facts，明确上下文下部分姓氏证据为中等
- [ ] HIGH/P1/P2/SAMPLE，去重、确定性抽样、完整命中计数、简洁 Markdown
- [ ] 复验原 ground truth、回归、压力及同一 11 份 DOCX
- [ ] 逐条语义审核，保存 provenance 与未决问题
- [ ] 整体代码审查、全量检查、提交并验证当前 HEAD 的远端 CI
- [ ] 核对 main 冲突与合并门槛，给出明确 readiness

Ruling: author_name_count 记录形态项数，采购/仓储为 shape=true、count=2、surname ratio=0，不在 Feature 层作作者结论；旧格式测试相应拆开。代价：该事实字段语义由姓名词表计数变为中文短项计数，文档同步说明。

Ruling: P1/HIGH 全部输出；P2 按角色+flag 签名默认 20，SAMPLE 默认 10，body-table agreement 默认 5；--max-per-flag 显式覆盖限额；多 flag 单条归最高优先级；命中总量始终不受过滤影响。代价：抽样不能代表全部语义正确，保留 --full。

Ruling: 用户计划本轮只允许编号层级筛选/标注，不按新发现扩展编号规则；确认类别错误则记录为合并阻塞。代价：可能给出 NOT READY TO MERGE。

Ruling: 部分姓氏在明确上下文中 scored=author/uncertain（中分75），原 selector 会 selected=author/preserved；保留该安全降级，修正 E2E 的 action 预期，不改变 selector。代价：部分姓名不自动套作者样式。

Ruling: 代理判断独立标明 reviewer_type=agent，未经用户认可不得冒称真人审核；等待用户对验收来源的选择，继续其他工作。代价：真正人工门槛未确认前不宣称通过。
