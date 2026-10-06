# DOCX Direct 真实文档语义与风险抽查

本阶段修复已确认的文前多作者脏 Heading 样式，以及旧式公式编号误升标题。不修改 Decision Selector、OOXML Patch、样式模板、页面设置、整体分数/分差阈值和 numbering family 的推断体系。

## 姓名列表

Feature 保留原 `person_name_pattern`，增加形态与姓氏事实：`author_name_list_shape / author_name_count / author_surname_match_count / author_surname_match_ratio`。形态只判断2～8个短项、每项2～4个汉字；分隔符为中文逗号、顿号、英文逗号、半角/全角连续空格，总长度不超过64。正文标点、数字、英文或超限项数不匹配。`author_name_count` 为形态项数，不是作者人数结论；姓氏事实使用 `COMMON_SURNAMES / COMPOUND_SURNAMES`，无单独“林”姓分支。兼容字段 `author_name_list_pattern` 表示形态成立且全部姓氏匹配。

姓名列表只是候选：题名后的4段以内、独立文前段落、非表格/列表/复杂对象，且随后最多3段内出现单位、日期、原生副标题或摘要线索时，Resolver 增加 `author_list_after_title`，对标题加入 `preface_author_conflict`。无上下文时 unknown/preserved，不因误套 Heading 自动升格。

全部姓氏匹配提供强作者证据；部分匹配但上下文明确提供中等证据，现有 hybrid selector 将冲突中的 author/uncertain 安全降为 author/preserved。全无姓氏匹配的“采购 仓储”等业务词不因形态或文前上下文变为作者。表格普通短项保持表格判定，不把所有短项列表当成表格外作者候选。

上下文不能越过正文、章节、表格或复杂对象借用日期。姓名后带机构名称和地址的单位行由 `author_affiliation_pattern` 提供有限文前证据；`body_started_before` 区分摘要本身成为正文边界与已经跨过正文的情形。原生 Heading 默认+95没有全局降低，冲突仅对姓名列表施加。

## 复杂对象

Analyzer 和 ElementAnalysis 增加 `has_embedded_object / has_math`，默认 false，兼容旧分析模型。检测 w:object、w:pict、o:OLEObject 与 m:oMath、m:oMathPara；Feature 保留细分信号并增加 `has_complex_object`（域/图形/嵌入对象/数学对象的聚合）。手工换行继续单独保护。

复杂段落不进入 `_safe_heading`、编号家族锚点或题名候选。unknown 获强保留证据，新嵌入/数学对象的普通角色受到更强负向证据，避免原生标题与数字深度累加压过对象保留。没有改动 high/medium 阈值。

转换策略已保护 object、pict、oMath、oMathPara，本阶段仅补验收：hybrid unknown/preserved 段落 canonical XML 不变；legacy 实验模式中若仍映射复杂段落，安全审计须 guarded/preserve，风险抽查标为 HIGH。

## 风险抽查器

```powershell
uv run python scripts/review_docx_decision_risks.py `
  --analysis artifacts/case/docx-analysis.json `
  --report artifacts/case/docx-normalization-report.json `
  --output artifacts/case/decision-risk-review.json `
  --markdown artifacts/case/decision-risk-review.md
```

脚本只读审计，不修改分类或 DOCX。要求有效且一致的源 SHA256、选择模式、评分配置、元素 ID 集合及 selected decision；禁止输出覆盖输入。旧审计缺新 feature 时列出 missing_feature_fields，不把缺失当成已经完成对象识别。

风险按元素去重并归最高等级：

- HIGH：复杂对象 mapped；原生 Heading 与姓名/单位/日期冲突且 selected 仍为 heading/mapped。
- P1：scored mapped 接管结构角色；文前 heading/mapped；表格外20字以内的 literal 编号 heading/mapped；scored 编号 family 标题与 legacy 层级不同。
- P2：其余 scored mapped 接管普通角色。
- SAMPLE：其余高分 mapped 且20字以内的文本。

HIGH/P1 默认全输出。P2 每种风险签名最多20，表格正文接管最多10；SAMPLE 每种签名最多10，表格正文 agreement 最多5。签名由等级、选择来源、角色和 flags 构成，每份文档按 document_order/element_id 固定取前 N 项。`--max-per-flag 20` 显式覆盖 P2/SAMPLE 限额；`--level P1` 可重复筛选等级；`--full` 输出所选等级全部候选。HIGH/P1 不受抽样限额影响。

summary 区分完整命中 `high / p1 / p2_total / sample_total / flagged` 与实际输出 `p2_sampled / sample_emitted / emitted_by_level / emitted`。过滤和抽样不改变完整命中量。JSON 保留前后各2段、完整 features、三套 decision 和选择原因；Markdown 只展示文本、上下文、flags、role/action、family/score/margin 和选择来源，便于逐条判断。

风险数量不是误判数量，HIGH=0不能证明全文语义正确。短表格内容计入完整命中，但默认报告只显示确定性样本；优先审核全部 HIGH/P1，再对 P2 分层抽查。

## 回归与真实资料边界

脱敏最小 DOCX 与 ground truth 位于 tests/fixtures/docx_direct_regression。build_fixtures.py 可重建：作者行故意套 Heading 3；公式包含不依赖真实二进制的 OLE/VML/OMML 节点。脏 Heading 6 公式不能污染正常第三级编号。测试走实际 DOCX/API/风险 CLI，并覆盖姓名分隔符、无上下文、正文边界、副标题、审计配对失败和结构安全。

真实论文不入库。六个反例来自本地 artifacts/real-docx-20261006/review-findings.json，逐一对照 element_id 和源指纹；修复后作者为 author，5个公式为 unknown/preserved，不在执行 ID 清单，整段 XML 原样保留。原8份真实资料继续执行结构验证。

本轮本地验证产物见 artifacts/real-docx-retest-after-semantic-fix/final 和 artifacts/semantic-new-sources/final。下一阶段先抽查不同来源文档中的高置信误判类别，不在本轮继续无限增加规则，也不合并 main。

## 合并 main 的门槛

最终证据保存至 artifacts/semantic-review-final：review-summary.json、review-decisions.json、review-notes.md 与 merge-readiness.json。实际审查必须保留 source SHA256、case、element_id、独立判断角色、selected 角色、correct/incorrect/pending、错误类别、理由及 reviewer_type。代理判断不可标为真人已确认；pending 不计为完成。重复审核须针对相同源指纹和当前分析。

必须同时满足：已知六个真实反例、31条 Ground Truth、作者/公式回归、压力和结构保护全通过；同一11份真实 DOCX 的源指纹和可见文本顺序不变；HIGH=0；P1全审核且没有未解决的类别型高置信误判；P2分层抽查无系统性问题；默认报告不再全量输出数千条短表格；作者泛化无单姓特判；pytest/Ruff/Mypy/前端测试与构建通过；GitHub Actions 对最终 HEAD 实际成功且六类检查均执行；相对最新远端 main 无未处理冲突；无已知数据损坏。

完整验收后必须明确写 READY TO MERGE 或 NOT READY TO MERGE，列出阻塞项。本轮只准备整合评估，不自动合并。编号家族类别错误仅标注记录；页数、字体、页面、页眉页脚、numbering.xml、表格重建和 Markdown/DOC 不属于本轮修复。
