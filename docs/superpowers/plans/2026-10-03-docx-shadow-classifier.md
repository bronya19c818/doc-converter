# DOCX Direct 第一阶段影子识别实施计划

目标：依据用户提供的完整第一阶段需求，为每段生成客观特征、全部角色候选、可加总证据、全文修正和保守判定；不改变现有 DOCX 写出决策。

架构：保留现有分类为 `classify_document_legacy`；`classify_document` 编排独立特征提取、评分、Resolver，并将影子结果附加到 legacy 的副本。Style Mapper 继续只读取原有 role/confidence/action。实现使用现有 Python、Pydantic、python-docx，不新增依赖。

## 全局约束

- 保留工作区已有修改；不改 Formatting Policy、Style Pack、API/UI、DOC/Markdown 路线。
- Analyzer 仅读取事实；区域和业务推断移至分类阶段。有效格式解析器保持原样。
- 阈值通过独立 ScoringConfig 配置；分数是启发式证据强度，不是统计概率。
- 新增验收只采用完整 DOCX 转换端到端测试，先写验收再实现；保存可复跑工件。

## 任务

- [x] 先编写 `scripts/verify_docx_shadow.py`：构造中文编号、数字层级、原生六级标题、元数据、题注、表格、参考文献、正文误判和不确定样本。捕获改造前输出、样式快照、legacy 决策和部件 SHA256，并确认影子验收失败。
- [x] 扩展 `model.py` 的候选、证据、决策和全文基线模型；新增 `features.py`（客观文本/编号/结构/格式/安全特征及基线）。
- [x] 新增 `scoring.py`：每个角色独立计算加减分；保留 raw_score；unknown 也参与竞争。
- [x] 新增 `resolver.py`：全文区域、编号家族顺序和原生级别锚点、文前顺序、参考文献、异常跳级修正。记录 context 证据，保留 resolved_score。
- [x] `classifier.py` 保留 legacy 原判定，再附加候选及 scored_decision；`audit.py` 同时序列化 legacy/scored 对比，展示最高分、次高分、分差和最终判定原因。
- [x] 运行端到端脚本，对比所有 DOCX ZIP 部件和源文件；再运行既有 Direct、压力测试和主路线回归、Ruff、Mypy；按 requesting-code-review 技能安排只读审查并修复有效问题。

## Review Focus

1. 单个大字号/粗体 run 不得把正文升为标题；正文主导字号采用字符加权基线。
2. 带句末标点的编号、自动列表、表内标题式文本不参与全文编号层级推断。
3. 相同编号家族多次出现保持一致；原生/outline 层级冲突需减分而非强判。
4. 无标题、无显式 Heading 的文章也应存在正文区域；表内“参考文献”不得改变全文区域。
5. 审计证据可重算 raw/resolved 分数；所有候选存在；影子结果与 legacy 存在分歧时成品仍与改造前一致。

## 验证结果

- 6份改造前基线文档，262段落：全部源SHA256、legacy决策和DOCX部件SHA256一致。
- 6组额外边界文档，18段落：孤立编号、手工操作清单、同字号文前短行、无标题短语、跨元数据副标题均保持保守判定；左对齐大字号题名正确识别。
- 完整API端到端工件：rtifacts/shadow-verified-20261003b/verification.json。
- 既有全量回归139通过：rtifacts/shadow-regression-final-20261003.xml。
- Ruff通过，Mypy的32个源文件通过，git diff --check通过。
- PDF预览未纳入本阶段验收；DOCX全部部件与基线一致。新增真实业务文档盲测和切换新评分驱动格式属于后续工作。
