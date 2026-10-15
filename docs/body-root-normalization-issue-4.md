# 最终正文根层级检查（Issue #4）

本轮只补最终结构检查，不改 Issue #3 的局部评分权重、不增加前端选项。继续 PR #2 的 `feat/issue-1-auto-normalization`，基线是 `7eae06953b45fda0b04215eee079c344532b46fa`。

## 复现与定位

`tests/fixtures/root_hierarchy/complete.md` 及同名段落生成的原生 DOCX 提供 H2/H4/H2 的完整正文。修改前 Markdown 的 `level_transform` 保留显式深度，最终决策和写出仍是 H2/H4/H2。DOCX legacy/shadow 保留原级别；hybrid/scored 将无编号原生标题按实际父节点压缩，虽得到 H1，却把 H2/H4 间距压为 H1/H2。另有显式 `outlineLvl` 的 Normal 段落，候选树会丢失同级闭合关系。这些问题发生在结构/最终决策阶段，不是样式编译器没有写出 H1。

另一个独立原因是 Markdown 首个 `# 总体要求` 遇到数字子标题时被推断成文档题名。现在共享的正文开篇标签判定阻止这类推断，保留真实 H1；显式 Front Matter 题名和真正的独立题名继续生效。

## 共享接口及执行位置

`structure/body_roots.py` 接受 `FinalParagraph`：最终角色、是否允许映射、源显式级别、编号/父节点/Regime/缺陷等既有事实。它不读取 Markdown token、Word XML、字号、评分权重，不创建标题或改编号文字。

Markdown 在第三阶段候选竞争完成后调用；DOCX 在 `select_decision` 和显式角色覆盖之后、`finish_source_audit` 以及 OOXML 映射之前调用。原始候选和 legacy/scored 决策保留，最终 `selected_decision`、有效层级和输出目标同步。DOCX 的 native Heading/DC_Heading 以及直接 `outlineLvl` 锚点均可输入，重新转换能识别自有标题样式。

检查只覆盖正文，附录/附件及参考文献是独立文后树，不用其 H1 代替正文根。边界要求明确语法和最终标题/参考文献角色，“附件应当……”或“附件管理要求”不会截断正文。

1. 从最终映射标题重建真实父子栈。缺父节点、虚拟父节点、冲突、受保护结构或未映射标题阻止全树调整。
2. 已有正文 H1 一般不重新定基；无编号的可靠原生树可以恢复候选压缩丢失的层级差。标题树的全部源锚点一致且父边一致时，也可恢复编号树的间距。直接 outline 锚点的重复同级根可恢复候选丢失的闭合关系。
3. 没有 H1 时，需要同级根、正文子内容、开篇章节标签、从 1 开始的根编号序列或独立题名等正向组合证据。孤立深层标题、部分数字路径、明确节选、独立根层级冲突均不因缺 H1 上移。
4. 确认完整正文整体偏移后，所有节点减去同一个 `min_root_level - 1`。H2/H3→H1/H2，H3/H4→H1/H2，H2/H4→H1/H3。原有父边、层级差、文字、编号、顺序不变。
5. 明确标注节选的 DOCX 若已经被候选层压缩，仅在全部可映射源锚点及父边一致时恢复原始深度。无法从内容判定完整性时，保留已有最终决策，不保证恢复每一项源样式深度；特别是未声明节选的编号材料仍受既有 schema 恢复规则处理。H1–H6 以外的既有保护策略不变。

审计 `body_root_normalization` 记录状态、原因、决策前根级别、源锚点根级别、offset、affected_ids、根/树 ID、before_tree/final_tree。`heading_tree` 继续保留候选结构证据；`final_heading_tree` 是正文输出决策树。单节点 `heading_level_before_root_check` 保留前值，`effective_heading_level` / `final_heading_level` 对应最终角色。候选分数仍是原始识别强度，最终层级检查不伪造新评分。

OOXML 映射器及保护清单保持原实现。字段/复杂对象、列表、表格等结构不参与可移动正文树，避免保护字段根却上移其余标题。标题样式和有效 outline 的落地继续由实际 DOCX 检查验证。

## 独立输出对照

`scripts/verify_body_roots.py` 的六组预先标注样本涵盖三种整体偏移、已有 H1 及层级差、节选、正文加独立附录。两条路径分别有 39 段实际输出检查、12 项应修正标题；检查真实 DOCX 样式和继承/直接格式合成后的 outline，并比较全部文本顺序。

| 同一输入、同一目标 | Issue #3 | Issue #4 |
| --- | ---: | ---: |
| Markdown 输出样式/层级错误 | 12/39 | 0/39 |
| Markdown 正确修正覆盖率 | 0/12 | 12/12 |
| DOCX hybrid 输出样式/层级错误 | 5/39 | 0/39 |
| DOCX hybrid 正确修正覆盖率 | 11/12 | 12/12 |

DOCX 的其他旧错误包括对节选过度压缩，以及既有 H1/H3 间距丢失，因此不能只看“应修复项”覆盖率。基线通过 `git archive` 冻结整个旧 `src`，包含旧共享解析器，避免混用新结构代码造成虚假对照。程序保存两版的源文件、DOCX、审计、逐段结果和耗时，`--check` 对当前输出错误返回失败。

## 原有语料及标注变更

保留 230 项合成语料和 223 项复杂语料的输入与角色身份。旧期望中有完整正文从 H2 开始的 17 项（合成 12、论文 5），与本 Issue 的目标直接冲突：仅这些正文标题的目标级别减 1，并保留 `issue4_previous_role`。附录不改；新增的显式标题修正进入应修正分母。以下采用同一份修订后真值对比两版，不能与旧报告原真值下的百分比直接相减。

| 指标 | 合成旧→新 | 复杂旧→新 |
| --- | --- | --- |
| 角色及级别正确 | 218/230→230/230 | 218/223→223/223 |
| 标题 Precision / Recall | 100% / 100%→相同 | 100% / 100%→相同 |
| 标题层级正确率 | 80.33%→100% | 95.73%→100% |
| 误修复数（未渲染口径） | 6→0 | 2→0 |
| 应修正数 | 69 | 131 |
| 正确自动修正覆盖率（未渲染） | 82.61%→100% | 93.89%→97.71% |

未渲染复杂语料的 3 项题注/参考文献样式修正无法确认，不算成功；CI 的 `--render` 对照补充实际样式，不能用 mapped 状态替代验收。该语料是受控样本，不代表所有业务文档的准确率。

## 回归及复现

针对性测试覆盖四种 direct 决策模式、编号/无编号标题、直接 outline、自有 Heading 样式再转换、真实 DOCX 样式及 outline、字段保护、明确节选、缺失数字父节点、虚拟父节点、独立 Regime、附录、题名误识别、无标题文档和风格切换。长文测试含 121 个标题和 60 条父子边，重复规范化及两次不同样式输出均核验。原有结构恢复、虚拟父节点、异常序列和 OOXML 回归继续运行。

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
npm test --prefix frontend
npm run build --prefix frontend
uv run python scripts/verify_body_roots.py --baseline-ref 7eae06953b45fda0b04215eee079c344532b46fa --check --output artifacts/body-roots
uv run python scripts/verify_markdown_scoring.py --baseline-ref 7eae06953b45fda0b04215eee079c344532b46fa --output artifacts/quality-issue4
uv run python scripts/verify_markdown_scoring.py --fixtures tests/fixtures/markdown_complex --render --baseline-ref 7eae06953b45fda0b04215eee079c344532b46fa --output artifacts/complex-issue4
```

CI 在已有完整 Python、Ruff、Mypy、前端、复杂语料实际 DOCX、DOCX-direct 角色/压力验收之外增加独立根层级输出对照；Docker 继续执行 CRLF 构建、真实启动/健康、MD/DOC/DOCX 转换和持久化重启。结果及样本在该次 CI 的两个 artifact 中，不改动生产前端流程。

性能记录：170,067 字节长报告进行 5 轮交替规范化，旧版中位数 0.1702 秒、新版 0.1384 秒；各轮为旧 0.1214–0.2304 秒、新 0.1179–0.2305 秒。这是同机测试负载下、不含渲染及 tracemalloc 的观测，波动范围重叠，不作加速结论。独立六文档端到端转换观测为 Markdown 9.08→10.59 秒、DOCX 6.11→7.55 秒，包含渲染、ZIP、审计 I/O，亦受并行测试影响。新增检查对最终段落/标题栈作线性扫描；性能不是本轮改造目标。

本机额外渲染五份 Markdown 复杂文档，208 项标注全部正确、204 项实际输出检查无差异、122 项应修正全部落地；真实 DOC 导入的第六份由 CI 的 LibreOffice 环境核验。
