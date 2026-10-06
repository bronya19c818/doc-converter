# DOCX Direct 真实文档语义与风险抽查

本阶段修复已确认的文前多作者脏 Heading 样式，以及旧式公式编号误升标题。不修改 Decision Selector、OOXML Patch、样式模板、页面设置、整体分数/分差阈值和 numbering family 的推断体系。

## 姓名列表

Feature 增加 `author_name_list_pattern / author_name_count`，保留原 `person_name_pattern`。支持2～8人，每个姓名2～4个汉字；分隔符为中文逗号、顿号、英文逗号、半角/全角连续空格，总长度不超过64。姓名首字使用现有常见姓氏集合，并补“林”。正文标点、数字、英文或超限人数不匹配。

姓名列表只是候选：题名后的4段以内、独立文前段落、非表格/列表/复杂对象，且随后最多3段内出现单位、日期、原生副标题或摘要线索时，Resolver 增加 `author_list_after_title`，对标题加入 `preface_author_conflict`。无上下文时 unknown/preserved，不因误套 Heading 自动升格。

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

筛选 scored mapped 接管、文前章节标题、短编号标题、复杂对象 mapped、原生 Heading 与元数据冲突，以及高置信20字以内文本。复杂对象 mapped 直接 HIGH；原生 Heading 与元数据冲突且仍映射为标题也为 HIGH。其他为 REVIEW，scored 接管优先排序。每条保留前后各2段、完整 features、三套 decision、selection 来源/原因和风险标志。

风险数量不是误判数量，HIGH=0不能证明全文语义正确。大量短表格内容会命中高置信短文本，人工应优先审查 scored 接管、章节编号及元数据冲突，避免把普通表格单元格当成已确认缺陷。

## 回归与真实资料边界

脱敏最小 DOCX 与 ground truth 位于 tests/fixtures/docx_direct_regression。build_fixtures.py 可重建：作者行故意套 Heading 3；公式包含不依赖真实二进制的 OLE/VML/OMML 节点。脏 Heading 6 公式不能污染正常第三级编号。测试走实际 DOCX/API/风险 CLI，并覆盖姓名分隔符、无上下文、正文边界、副标题、审计配对失败和结构安全。

真实论文不入库。六个反例来自本地 artifacts/real-docx-20261006/review-findings.json，逐一对照 element_id 和源指纹；修复后作者为 author，5个公式为 unknown/preserved，不在执行 ID 清单，整段 XML 原样保留。原8份真实资料继续执行结构验证。

本轮本地验证产物见 artifacts/real-docx-retest-after-semantic-fix/final 和 artifacts/semantic-new-sources/final。下一阶段先抽查不同来源文档中的高置信误判类别，不在本轮继续无限增加规则，也不合并 main。
