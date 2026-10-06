# DOCX Direct 合并前收尾执行记录

范围以用户收尾计划为准：作者姓氏事实泛化、风险分级/去重/确定性抽样、11 份真实文档复验、独立审核记录与 HEAD 的 GitHub CI。不得改 selector、policy、OOXML patch、全局阈值、编号家族推断、样式、页面和 Markdown/DOC 路线。

起点：d154ef9，experiment/docx-direct-normalizer。既有 CI 未提交改动为创建 artifacts 目录，保留并验证；.codegraph/ 为既有未跟踪目录，保留。

- [x] 先写 DOCX/API/CLI 端到端反例，观察失败（13失败）
- [x] 泛化作者 shape/surname facts，明确上下文下部分姓氏证据为中等
- [x] HIGH/P1/P2/SAMPLE，去重、确定性抽样、完整命中计数、简洁 Markdown
- [x] 复验原 ground truth、回归、压力及同一 11 份 DOCX（31 GT、6真实反例、结构11/11）
- [x] 逐条代理语义审核，保存 provenance 与未决问题（P1=448，代理incorrect=204，pending=13；真人确认未获）
- [x] 整体代码审查与本地全量检查（190后端、26前端、Ruff/Mypy/build通过）
- [x] 核对 main 冲突与合并门槛（无冲突；类别型语义错误阻塞 main）
- [ ] 最终 HEAD 远端 CI（动态结果见 artifacts/semantic-review-final/github-ci.json）

Ruling: author_name_count 记录形态项数，采购/仓储为 shape=true、count=2、surname ratio=0，不在 Feature 层作作者结论；旧格式测试相应拆开。代价：该事实字段语义由姓名词表计数变为中文短项计数，文档同步说明。

Ruling: P1/HIGH 全部输出；P2 按角色+flag 签名默认 20，SAMPLE 默认 10，body-table agreement 默认 5；--max-per-flag 显式覆盖限额；多 flag 单条归最高优先级；命中总量始终不受过滤影响。代价：抽样不能代表全部语义正确，保留 --full。

Ruling: 用户计划本轮只允许编号层级筛选/标注，不按新发现扩展编号规则；确认类别错误则记录为合并阻塞。代价：可能给出 NOT READY TO MERGE。

Ruling: 部分姓氏在明确上下文中 scored=author/uncertain（中分75），原 selector 会 selected=author/preserved；保留该安全降级，修正 E2E 的 action 预期，不改变 selector。代价：部分姓名不自动套作者样式。

Ruling: 代理判断独立标明 reviewer_type=agent，未经用户认可不得冒称真人审核；等待用户对验收来源的选择，继续其他工作。代价：真正人工门槛未确认前不宣称通过。

Ruling: CI先证实产物目录缺失，再暴露现有夹具写死pandoc.exe；只修测试的平台文件名，不改生产渲染路线。代价：需在Linux再次跑完整workflow确认。

Deferred minor: review_risks(levels=[])直接Python调用会输出0条，但sampling.levels误记为全部；CLI不能产生该输入，不影响本轮审核。保留低优先事项，不以额外重构扩大范围。

验证记录：713080f先提交测试，bcc904f作者泛化，adceb27风险工具，78fc09f文档门槛与CI目录修复。真实资料只存本地artifacts，不入Git。默认完整命中8,876，实际输出602（P1=448，P2=36，SAMPLE=118），总分析12,192。P1代理标注中的90条清单误升标题、114条局部层级错误另留独立记录，不进入本輪规则修复。
