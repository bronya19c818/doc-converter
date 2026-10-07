# DOCX Direct 角色转换与有效格式验收

链路为 `Analyzer → Scoring / Resolver → Decision Selector → selected_decision + StylePack → Role Policy → Executor → DOCX → Effective Formatting Verification`。转换层不重判语义；[决策选择说明](docx-selected-decision.md)描述发布模式。标题评分、序列、层级体系与源结构恢复保持独立。

## 角色支持矩阵

所有角色都可在 StylePack 中配置。自动识别表示有识别入口，执行仍受 selected action 和结构安全检查约束。

| 角色 | 状态 | 自动识别证据 | 段落／字符执行 |
| --- | --- | --- | --- |
| document-title、document-subtitle | supported | 文前题名 | 是／是 |
| organization-department、author、date | supported | 元数据 | 是／是 |
| heading-1、heading-2、heading-3、heading-4、heading-5、heading-6 | supported | selected 层级 | 是／是 |
| body-paragraph、body-table | supported | 正文／表格上下文 | 是／是 |
| table-caption、figure-caption | supported | 题注 | 是／是 |
| reference-heading、reference-entry | supported | 参考文献区域和条目 | 是／是 |
| abstract-label、keywords-label | supported | 明确中文标签与中英文冒号，或单独标签 | 是／是 |
| abstract-content、keywords-content | supported | 同段标签后字符区间 | 否／是 |
| table-column-header | supported | 最近所属行显式 w:tblHeader；val=0 不激活 | 是／是 |
| table-row-header、point | preserve-only | 样式可配置，暂不自动赋值 | 否／否 |
| image、footer、page | out-of-scope | 源对象、页眉页脚和全局页面保留 | 否／否 |

完整机器可读矩阵为报告的 `role_capabilities`。不猜首行或首列，外层表头标记不传给嵌套表格。

## 角色策略

| 策略族 | selected role | 规则 |
| --- | --- | --- |
| heading-strong | H1–H6 | 普通文字目标字体、字号、粗斜体、颜色，outline=N−1 |
| structural-metadata | 题名、副标题、作者、单位、日期、参考文献标题 | 目标基础格式，非标题 outline=9 |
| caption-strong | 图表题注 | 题注格式接管，原文和结构保留 |
| body-mixed | 正文 | 基础格式统一，局部语义保留 |
| table-body-mixed | 表格正文、显式列头 | 文字与段落统一，几何结构保留 |
| reference-mixed | 参考条目 | 混合正文规则，文献原文、编号和链接保留 |
| composite-metadata | 摘要／关键词 | 标签段落样式＋内容字符样式 |
| preserve | unknown、无策略角色、非 mapped action | 源段落和 Run 保留 |

mapped 段落清除源 alignment、非编号 ind、spacing、keepNext、widowControl、pageBreakBefore、outlineLvl 覆盖，交由目标样式控制。段落分页属性与手工 `<w:br w:type="page">` 分开处理，后者保留。ParagraphStylePreserver 只物化继承编号和编号缩进，读取 upsert 前的原始源样式。

普通文字统一 rFonts／sz／szCs。正文 b／bCs、i／iCs、color、u、highlight 仅在全段直接属性一致且没有字符语义或受保护文字证据时清除；局部强调和上下标保留。超链接文字可以规范字体和字号，包装、关系、语义颜色和下划线保留。

源字符定义不改，稳定的 DC_PolicyChar 派生链过滤源视觉覆盖并保留字符语义。复合元数据派生链以 DC_AbstractContent／DC_KeywordsContent 为基底，保留各层语义，避免粗体等 toggle 属性被扁平化。缺失或循环继承按具体 Run 保守处理。

## 复合元数据与托管样式

`inline_segments` 使用源 ElementAnalysis.text 的 start／end 偏移。标签应用 DC_AbstractLabel／DC_KeywordsLabel 段落样式，同行内容应用 DC_AbstractContent／DC_KeywordsContent 字符样式。支持单 Run、标签跨普通 Run、内容局部强调与完整内容超链接。

只拆分直接所属段落的普通文字 Run，保留分割空白的 xml:space。标签或分割边界位于超链接、域、修订等容器时整段保留，不重建复杂节点。内容中的域结果跳过；表格单元格中的“摘要”等不触发文档元数据角色。

支持和 preserve-only 角色的 DC 托管定义安全 upsert；point／行标题的样式可更新，但不因此自动赋予这些角色。图片和页脚样式不更新，非 DC 源定义不变。A→A／B→B 幂等，A→B 更新已有定义，不追加 Heading1_2。Direct 编译补充不影响共享 Markdown 渲染器。

换段落样式前比较受保护 Run 的源有效字体、字号、粗斜体、颜色、上下标等；若它会继承不同格式，保留整段，不只保留节点字节。upsert 同样检查已有托管定义对受保护片段的间接影响，冲突定义列入 guarded_style_ids 并保留。整段受保护而跳过的记录有具体原因，不能按 mapped 决策计为已执行。段落／Run 的 preserved 状态描述执行动作；托管定义的更新独立记在 style_injection。

numPr、numId／ilvl、numbering.xml、编号缩进、书签、域代码、脚注尾注引用、图片、OLE、公式、修订、制表符、手工换行／分页、分节及关系不重建。纯受保护文字段整段跳过，混合段仅处理允许的普通 Run。表格 tbl／tr／tc、tblPr／tblGrid／trPr／tcPr、合并、宽高和嵌套结构保留。源上传文件只读。

## 审计与复跑

报告包含 selected role／action、target_style、policy_family、transform_safety、removed／preserved／skipped 属性及原因。expected_role_style、style_application_status（applied／guarded／preserved／skipped）、effective_style_after、effective_format_after、effective_format_match 与 format_checks 来自实际输出的重新分析。

后验核对目标样式、outline、各字体槽位、普通／复杂文字字号及粗斜体、缩进／间距／行距和分页等明确配置。编号缩进、局部语义、链接颜色或无法解析的字符链逐项标明 excluded_reason。受保护 Run 独立核对转换前后有效格式，变化则取消输出提交。guarded 的目标 match 表示其余受控项匹配，不代表排除区域已转换；未执行段 match=null。

有效格式保护／后验核对使用 Word 的样式层开关语义（[MS-OI29500 2.1.230](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/f7130225-2368-48f3-acae-a9d278d0fb25)），字符内容角色相对标签基线编译，避免普通摘要内容继承标签粗体。原始分类特征解析保持阶段一兼容；严格解析只用于执行安全检查和输出格式验收。

使用新目录，保存源 DOCX、输出、审计和 verification.json：

```powershell
uv run python scripts/verify_docx_roles.py --output artifacts/role-acceptance-new
uv run python scripts/verify_docx_shadow.py --decision-mode hybrid --acceptance --edge-cases --output artifacts/selected-acceptance-new
uv run pytest -q
uv run ruff check .
uv run mypy src
npm --prefix frontend test
npm --prefix frontend run build
```

CI 保留专用角色及既有 selected／压力验收工件；私有文档和人工标注仅在本地复跑。版式验收采用 soffice.com、独立 UserInstallation 与 Poppler 原生程序，检查技术规范书、作者／公式、问卷的代表页。固定行高和不拆分表格仍是源布局边界；结构保持或 API 成功不代表所有页面都适合新字号。

预览的私有 LibreOffice profile 配置标准中文／英文同字体别名（例如仿宋／FangSong），解决中文字体名被误替换为 MS UI Gothic 的本地渲染问题；不改 DOCX 字体、fontTable、用户 LibreOffice 配置或系统字体安装。依据[LibreOffice 官方字体替换接口](https://docs.libreoffice.org/svtools/html/fontsubstconfig_8cxx_source.html)，仅配置当前临时 profile。Office 使用短临时目录中的英文文件名副本；完整 PDF 在目标目录暂存后原子发布，避免深路径和跨盘移动问题。Windows 实际 PDF 字体验收需安装的 FangSong／LibreOffice，并设置 DOCX_FONT_AUDIT_PYTHON 指向带 pypdf 的检查运行时；CI 无该字体时明确跳过，普通跨平台 DOCX 验收继续执行。
