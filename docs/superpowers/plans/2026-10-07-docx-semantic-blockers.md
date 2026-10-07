# 两类语义阻塞修复执行记录

此计划的局部H4/H5猜测已被用户后续明确的标题体系/压缩/章节树规范替代，后续执行见 [标题体系记录](2026-10-07-docx-hierarchy-schema.md)。本文件保留原决策过程，87条真实源GT提案仍未标为业务确认；不得把旧代理建议直接当真人真值。

起点85420a4，experiment/docx-direct-normalizer。保留既有.codegraph/及私人artifacts。用户计划明确先得到业务GT，不将204条代理判断作为算法GT；13条问卷必须由业务确认或明确unknown/preserved。

本轮沿用executing-plans、TDD和最小改动流程：先准备可逐条审查的GT和用户已明确给出的结构例，再按获确认GT实现手工序列证据、局部标题栈，最后重新做离线评估、11真源、完整测试、代码审查、HEAD CI和merge gate。

冻结selector/policy/mapper/OOXML/style/pages/Markdown/DOC；保留global prior和hierarchy_jump，不扩大正式Role taxonomy。

- [x] paired source/hash/IDs与业务GT清单（30列表、44层级、13问卷，共87；expected=null）
- [ ] 30列表、44层级、13问卷的业务确认
- [x] 先写并观察DOCX/API E2E反例（用户明确结构例，11项均失败；未改生产算法）
- [ ] 手工连续序列证据（无主题关键词规则）
- [ ] 独立heading_hierarchy模块、局部parent/family/decimal证据
- [ ] 已确认GT离线前后对比，原231 correct保护
- [ ] 同一11真源、6已知反例、31GT、压力、全量检查
- [ ] 新候选的独立proxy审核及business/automated provenance
- [ ] 代码审查与当前HEAD CI，明确merge readiness

Pre-flight: GT→E2E→manual sequence→local hierarchy→evaluation共享role/action/source ID；expected未确认时不得作为business GT使用。标题栈应排除强手工列表、表格、列表域、复杂对象和元数据；hierarchy_jump必须在local evidence之后。

Ruling: 90条依据清单代理误判仅在一份技术规范中，用户覆盖三来源要求无法仅靠这些90条完成；选20条原问题加另两来源10条真实列表控制，明确区分，代价是另10条不是旧误判修复样本。

Ruling: 真人业务GT通过结构化清单一次性确认，批准前reviewer=proxy_review、expected=null；可以先写用户计划中已明确expected的独立合成E2E，不能把代理旧建议当已确认GT推进算法。代价：真实层级修复依赖业务回复。
