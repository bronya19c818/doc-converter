# DOCX Direct 转换策略（第二阶段）

实际链路为 `Analyzer → Scoring / Resolver → Decision Selector → selected_decision → policy_for_role → 段落与字符策略执行 → DOCX`。选择与发布模式见 [决策选择说明](docx-selected-decision.md)。策略对象不可变，属性模式支持 `replace / preserve / discard / conditional`。

| 策略族 | selected role | 执行规则 |
| --- | --- | --- |
| structural-strong | 文档题名、副标题、作者、单位、日期、H1–H6、图表题注、参考文献标题 | 目标角色样式接管段落基础排版，以及普通文字的字体、字号、粗斜体、颜色 |
| body-mixed | 正文、参考条目 | 统一基础字体、字号和段落排版，保留局部粗斜体、上下标；颜色、下划线、高亮等仅在整段直接覆盖一致且没有语义或受保护文本证据时清除 |
| table-body | 表格正文、首行与首列标题 | 规范文字及基础段落排版；编号相关缩进保留；表格、行、单元格、宽高、边框、底纹、网格及合并结构均不重建 |
| preserve | unknown、无策略的角色、action 非 mapped | 保留原段落及字符格式 |

`formatting.py` 分别提供 `apply_paragraph_policy` 和 `apply_run_policy`。旧 `clean_uniform_direct_formatting` 仍保留为正文混合策略的兼容入口。XML-only `patch_document_xml` 没有可写 styles 部件，因此对非中性字符样式保守处理；正式 normalizer 使用 `patch_document_parts` 同时提交 document/styles。

## 继承与结构保护

字体和字号也可能来自字符样式的 basedOn 链。`character_styles.py` 按策略增加派生字符样式，过滤被目标样式接管的视觉属性，保留字符语义属性和原样式定义。缺失、循环或无法安全解析的字符样式不会被强行重写。

`paragraph_styles.py` 在更换 pStyle 前，将源样式中的继承编号、编号缩进、分页等保留属性保存为直接属性。它不修改 numbering 部件，也不重建列表；源段落样式继承不可解析时，整段跳过。

超链接的关系与文本、书签、脚注尾注引用、域代码、域结果、图形、图片、公式、制表符、手工换行、分页、修订和分节等节点不删除。域、修订、图形、公式及引用相关 run 不进入普通格式清理；复杂域上下文跨段落跟踪，整段均为域结果时，段落和字符格式一起保留。超链接普通文字允许规范字体/字号，链接包装、关系和语义属性继续保留。

`transform_safety` 与 role 独立：`safe` 为普通映射；`guarded` 为含受保护结构、继承属性或无法安全解析的字符格式；`preserve` 为整段跳过。它不回写 classifier 的 role、action 或评分。

## 审计与验证

`docx-normalization-report.json` 每段包含 `policy_name / policy_family / transform_safety` 及 `removed_properties / preserved_properties / skipped_properties`，每项记录层级、数量、模式和原因。字符样式过滤逐项记录字体、字号、粗斜体等属性，数量按每个受影响 run 的继承节点计数，不表示删除原样式定义。`classification` 分别统计三套识别；`counts / xml_patch.mapped_count / skipped_count` 描述 selected 的实际执行情况。

新增测试先于对应实现编写，涵盖完整 DOCX 转换、字符样式继承、表格与复杂节点、未知内容原样保留、源样式继承编号/分页及跨段落域结果。可复跑压力验证通过应用 API 上传、转换、下载，并保留 DOCX、审计和 `verification.json`：

```powershell
.\.venv\Scripts\python.exe scripts/verify_docx_policy.py --output artifacts/policy-acceptance-new
# 可用 --source "C:\path\document.docx" 加入真实文档，原文件只读。
.\.venv\Scripts\python.exe scripts/verify_docx_shadow.py --decision-mode shadow --baseline artifacts/shadow-baseline-20261003d --shadow-reference artifacts/shadow-verified-20261003-final --output artifacts/policy-shadow-new --policy-output --edge-cases
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe src
```

每次验收使用新的输出目录。shadow 脚本默认仍严格比较输出 ZIP 部件；`--policy-output` 显式允许 document/styles 的视觉变化，并比较 legacy 决策、影子证据/评分、结构及其他部件；旧基线缺少影子字段时，通过 `--shadow-reference` 指定第一阶段已验证的输出目录。

版式检查使用 `soffice.com`，每次独立 UserInstallation，先导出 PDF 再用 Poppler 原生程序生成页面图片。ZIP 结构不变并不等于版式适合所有目标字号；固定行高或复杂对象仍需结合页面检查。此阶段不修改页面、表格几何或编号定义，也不替换 scored classifier。
