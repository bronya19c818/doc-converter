# DOCX Direct 影子结构识别（第一阶段）

`classify_document()` 对 Analyzer 原始证据运行特征提取、独立角色评分和全文修正，随后运行原分类器。返回元素的 `role / confidence / action / reasons / region` 仍是 legacy 结果，Style Mapper 的输入不变。

## 审计字段

`docx-analysis.json` 包含：

- `classification_mode: legacy-with-shadow`。
- `document_baselines`：正文主体字号、全文与正文的字符加权字号分布、文前最大主导字号、常见正文样式和对齐方式、编号家族推断与冲突。
- `scoring_config`：本次影子运行实际使用的阈值和权重覆盖。
- 每段的 `features`、18 个 `candidates`、`legacy_decision` 和 `scored_decision`。元素顶层区域属于 legacy；`features.region` 是独立影子区域，两者允许不同。

候选证据中的 `stage=raw` 为段落自身证据；`stage=context` 为全文区域、文前顺序、编号家族或层级跳跃修正。`raw_score` 等于全部 raw 贡献之和，`resolved_score` 等于全部贡献之和；分数不裁剪，因此负数和超过 100 都有效。

`scored_decision` 保留第一候选 `top_role / score`、第二候选 `runner_up_role / runner_up_score`、`margin`、最终 `role / confidence / confidence_band / action / reasons`。证据不足或分差小于歧义阈值时最终角色可以是 unknown，第一候选仍可追溯。

`docx-normalization-report.json` 保留原有输出记录，同时增加每段的 legacy/scored 对比与全文分歧计数。原有 mapped/uncertain/preserved 统计继续描述实际 legacy 输出，不能当作新评分统计。

## 调整阈值

后端识别调用可传入独立配置，不修改样式包：

```python
from doc_converter.docx_direct.classifier import classify_document
from doc_converter.docx_direct.scoring import ScoringConfig

result = classify_document(analysis, scoring_config=ScoringConfig(
    high_score=85, medium_score=65, high_margin=15, ambiguous_margin=5,
    weights={"heading_bold": 4},
))
```

配置只影响 scored 决策。默认高置信要求最高分至少 85、分差至少 15；中置信要求最高分至少 65。自动列表、空段落和复杂对象允许 unknown/preserved；异常标题跳级禁止 mapped。confidence 是依据分数及分差计算的启发式强度，不是统计概率。

中文编号家族按全文安全候选的出现顺序推断，原生 Heading/独立 outline 层级提供锚点，重复家族保持一致；数字多级编号独立记录深度。表格、完整正文句、列表和复杂对象不参与编号家族推断。孤立或混合编号体系仍需真实样本校准。

## 可复跑验收

先在改造前采集基线，再用相同源 DOCX 和样式快照验证：

```powershell
.\.venv\Scripts\python.exe scripts/verify_docx_shadow.py --capture-baseline artifacts/shadow-baseline
.\.venv\Scripts\python.exe scripts/verify_docx_shadow.py --baseline artifacts/shadow-baseline --output artifacts/shadow-verified --edge-cases
```

每次使用新的输出目录。脚本通过真实应用 API 执行上传、Direct 转换和产物下载，保存源文件、产物、审计和 `verification.json`；逐个比较 DOCX ZIP 部件 SHA256，而非易受 ZIP 时间戳影响的整包字节。默认通过缺失预览引擎的受支持配置跳过 PDF 预览，添加 `--with-preview` 可启用本地预览。

覆盖文前五类角色、原生六级标题、中文与数字编号、正文竞争、表格、题注、参考文献、自定义样式、局部大字号粗体、异常跳级，左对齐大字号题名、无标题短语、单一家族手工操作清单，以及项目原有压力文档。脚本不接入新格式策略，也不修改原始输入。
