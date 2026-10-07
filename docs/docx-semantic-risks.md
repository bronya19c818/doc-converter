# DOCX Direct 真实文档语义与风险抽查

本阶段修复文前多作者脏 Heading 样式、旧式公式编号误升标题及编号列表污染标题体系。Decision Selector、OOXML Patch、样式模板、页面设置、整体分数/分差阈值保持不变。

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

完整验收后必须明确写 READY TO MERGE 或 NOT READY TO MERGE，列出阻塞项。本轮只准备整合评估，不自动合并。页数、字体、页面、页眉页脚、numbering.xml、表格重建和 Markdown/DOC 不属于本轮修复。

## 标题体系与章节树

`manual_sequences.py` 先提取连续编号、相邻子内容、样式与直接格式比例、文本形态和序号路径。至少三个无子正文的平行条目提供强列表证据；没有独立标题锚点、仅末项接正文的相邻编号提供不确定证据。列表不进入标题树或激活层。检测不依赖“标准”“办法”等业务词。

`hierarchy_resolver.py` 只提供可审计的角色证据。先判断标题资格，再选择中文综合材料、常规报告或数字技术规范体系。章、节、中文序号、中文括号、阿拉伯序号、阿拉伯括号、圈号的理论顺序不代表固定H1–H6：当前体系未启用的层不占级别。数字技术体系保留编号路径深度。附件、分节、重复第一章和稳定数字根可开始新体系；明确原生父容器允许嵌套，退出时恢复外层树。

无编号标题不占编号层，其实际层级来自有效父节点加一，无父为H1。原生大纲帮助判断资格和父/同级关系，不能直接把源Heading N当成有效N。显式体系边界隔离标题资格证据，禁止借用前一节的编号伙伴。

审计包含 `hierarchy_schemas / hierarchy_regimes / heading_tree / hierarchy_warnings`。每个regime的 `compressed_levels` 表示局部压缩层，`base_level` 为父节点有效级别，`effective_levels` 为实际级别。每段包含资格区段、体系、有效级别、父ID及警告。全文 `numbering_family_levels` 仅保留为兼容历史先验，不驱动选择；`effective_numbering_family_levels` 只列所有体系中一致的有效家族层级。

已有heading likelihood在目标层级之间重新分配（匹配+40、其他-35），不把所有编号统一加成高置信标题，也不更改阈值。真实跳级、深度超过H6、父节点超限或中文体系数字条款缺少当前前缀父节点时保守保留；不得钳制为H6或从其子体系重新生成H1。明确原生父下重新从1编号的系列可形成子体系，连续同级保留在子体系内，父级peer或新的数字根关闭内层范围。审计中的树节点是结构假设，是否实际映射仍由selected decision及转换策略决定。

本轮验收依据用户明确给出的层级规则及DOCX/API端到端反例。旧真实文档代理标签按新规则重新解释，不能冒称真人GT；模型输出不能作为期望值。最终226项后端、26项前端、31条原基准与压力验证通过；同一11份真实源的12,192段及六个作者/公式反例通过保护校验。

90条依据列表不再升标题；原114条层级代理反例按新规则比较，70条正确映射、44条因缺少可确认的编号父节点保留，不能把保留算成正确映射。原13条问卷按H1/H2规则全部映射。历史114条标签来自旧代理，其中部分层级定义已被用户新规范替代，前后正确率不能直接使用旧标签分母。

风险重点候选540条P1已覆盖源上下文代理比较，其中522条规则/源结构一致、18条待业务确认；85条默认P2样本未见系统性问题。代理审核不代表真人验收。最终本地复跑、风险账本、警告与合并结论保存在 `artifacts/hierarchy-schema-v3/final-validated`，公开代码不包含真实DOCX；当前仍有未决案例，状态为NOT READY TO MERGE。
