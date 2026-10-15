# 主标题、副标题与正文 H1 的共享表达证据（Issue #5）

本轮基于已合并 PR #2 的 main `45827fb46d27df9454d3680fcb6cb2252c6842d5`，使用独立分支 `feat/issue-5-title-semantics`。不改变一键转换、前端设置或人工确认流程，不引入模型、网络服务或新依赖。

## 复现与定位

旧 Markdown 主要依靠首个 `#`、文种后缀和破折号副标题。一旦文前第一段漏判，单向的 preface/seen 状态也会影响后续副标题。旧 DOCX 对原生 Heading 加分、对题名候选扣分；同字号、不居中的封面题名常输给章节候选。错误在最终角色竞争之前产生，样式映射器只是忠实执行了错误的 H1；Issue #4 的根归一化无法替代角色身份识别。

`tests/fixtures/title_semantics/cases.json` 在实现前固定 20 例逐段真值，两条路线合计 40 场景。首次红灯为 26 个场景失败。样本覆盖无文种后缀、无破折号、错误 Heading 1、普通段落题名、无副标题、仅正文 H1、正文含报告/研究/方案、多行/手动换行题名、作者单位顺序、中英混排和原生 Title/Subtitle。`holdout.json` 是核心规则完成后另写的 8 例验证集，未为其两个残余错误追加个例规则；它不是盲测或随机业务语料。

## 共享接口与决策顺序

`structure/title_semantics.py` 提供两个接口：

- `semantic_profile(text)` 输出三个独立分数、原型版本 `title-expressions/v1`、命中表达、语义槽位及反例。主题转换、研究对象与属性、并列主题、文种表达支持题名；案例、来源证据、研究视角支持副标题；编号、局部章节范围和正文长句构成不同方向的证据。分数是启发式证据，不能解释为概率。
- `select_title_area(TitleParagraph[])` 比较有限文前区域的封面与正文假设。适配器只传文本、源层级、明确 Title/Subtitle、格式支持及保护/元数据事实，不传另一条路线的字号权重或候选结果。窗口最多 12 个非空段落，正文长句及保护块关闭搜索；明确摘要标签可作为封面结束边界，避免摘要正文先于章节而阻断题名识别；后续独立章节、题名与范围补充的相邻关系、词项重叠及案例/视角表达共同进入审计。

弱题名形状必须得到副标题组合或居中且较大字号的额外支持。没有副标题是正常状态。已有明确 Title/Subtitle 和 Markdown Front Matter 保持优先。两段仅在第一段具有语法续接信号时组合为多段题名，不把相邻完整主题任意合并。真实 H1 的 H2 子节不能仅凭章节措辞就被视作新正文根；必须有额外封面组合或格式证据。正文开始后的相似表达不参加文档级身份提升。案例/视角表达只表明范围补充关系，词项匹配无法判断现实世界中两个主题是否相关，这属于规则边界。

Markdown 在逐段状态推进前先形成文前联合假设，再将原型分数和 `title_subtitle_relation` 加入局部候选，随后复用原有序列/全文层级解析与最终竞争。编号已有独立评分，因此语义 H1 证据不对编号重复加分，非编号增量有上限。DOCX 在特征提取后做同一联合比较，再经过原有 scoring → resolver → decision_selector；确认封面后修正原始 Heading 的竞争关系，**最终 hybrid/scored 的 selected_decision 真正改变**，不是只写审计。legacy/shadow 仍保留历史决策供对照。

两路都在最终主副标题身份确定后调用 Issue #4 的 `normalize_body_roots`。已确认封面不再参与手工编号/章节候选树，避免错误父节点反过来影响正文。没有替换已有的层级恢复、虚拟父节点、冲突审计或 OOXML 执行器。

## 写出与稳定性

DOCX 错用 Heading 1 的封面写成 `DC_DocumentTitle` / `DC_DocumentSubtitle`，有效大纲应为未设置或 body level 9；正文 H1 写成 `DC_Heading1` 且有效大纲 0。识别新增自有题名样式，第二次转换不退回章节。手工换行题名可改段落样式，但字段、公式、图形等复杂内容仍受原保护规则约束。

Markdown 多段题名按原段落顺序保存在标准 Front Matter 值中，重复规范化稳定；序列化和渲染遵守元数据插入顺序，修复新识别封面暴露的作者/单位重排。实际输出验证也展开 Front Matter 的题名段落，检查主副标题有效大纲，不能用候选已选中替代写出验收。

## 验证与复现

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
npm test --prefix frontend
npm run build --prefix frontend
uv run python scripts/verify_title_semantics.py --baseline-ref 45827fb46d27df9454d3680fcb6cb2252c6842d5 --render --benchmark --check --output artifacts/title-semantics
```

质量脚本用 `git archive` 冻结整个旧 src，由独立进程运行同一标注输入；不混用新解析器。每版保存源 Markdown/真实 DOCX、规范化文本、审计、实际 DOCX、逐段角色及样式/大纲检查。`--check` 要求开发集无错误，验证集每路最多一个已知漏识别，且题名/副标题无 false positive。长文性能样本含 602 段，100 个章节、500 段正文及两段封面；预热一轮后记录五轮中位数，排除渲染及审计磁盘写入，分别计 Markdown 规范化和 DOCX 分析+分类。

CI 保留完整 Python、Ruff、Mypy、前端、230 项旧合成、223 项复杂语料、正文根、实际角色样式和压力文档验证；新增旧 main 对照。Docker 仍执行 CRLF 镜像构建、真实启动、健康检查、MD/DOC/DOCX 转换与持久化重启。所有样本和报告随 CI artifact 发布。

质量指标、具体误判及局限见 [识别质量报告](title-semantics-quality-issue-5.md)。
