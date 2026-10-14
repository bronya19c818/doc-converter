# Markdown 多阶段结构恢复与 DOCX-direct 复用边界

本轮在 Issue #1 / PR #2 的一键转换基础上完成 Issue #3。产品流程仍为选择文件、一次点击转换、预览和下载。MD 与 DOC 导入走 Markdown 原生结构证据；DOCX-direct 保留评分、决策融合和原包 OOXML 执行路径。

## 共享编号与结构能力，保留各格式的证据和执行方式

| 模块 | 本轮处理 | 负责内容 |
| --- | --- | --- |
| `docx_direct/analyzer.py`、`effective_format.py`、`features.py` | 保留；features 的原编号解析提取到共享包 | 段落、对象、表格、编号与有效格式继承；字体和字号证据仅属于 DOCX |
| `structure/numbering.py` | 从原 features 原样提取 | 编号家族、编号路径、中文数字及圈号序号；不判断角色 |
| `structure/manual_sequences.py` | 原序列实现迁移，旧路径重导出 | 连续序号、平行形态、各项是否拥有子正文；区分人工列表与章节 |
| `structure/hierarchy_resolver.py` | 原章节模型迁移，保留默认行为 | 标题资格、Regime/Schema、有效层级压缩、编号父子图、缺失父级和冲突警告 |
| `structure/source_structure_recovery.py` | 原源结构恢复迁移，旧路径重导出 | 先找真实未编号父标题，再用已印证的同父模板建立内部虚拟父节点；不编辑 Word 或 Markdown |
| `docx_direct/resolver.py`、`scoring.py`、`decision_selector.py` | 保留原决策 | DOCX 区域证据、格式权重、legacy/scored/hybrid 竞争和冲突处置 |
| `explicit_roles.py`、`style_mapper.py`、`format_verification.py` 等 | 保留 | OOXML 结构保护、角色样式执行、写入后的有效格式复核 |
| `markdown_scoring.py` | 三阶段决策 | Markdown token/行范围、独立权重、元数据竞争、共享结构适配、最终角色 |
| `normalizer.py`、`renderer.py`、`markdown_verification.py` | 自动执行和输出复核 | 原文切片修正、Pandoc 渲染、实际样式、大纲及有效格式核验 |

共享接口继续接受纯字典结构事实和候选证据容器。Markdown 没有字号、字体和继承样式证据，适配器相应字段为 `None`；共享结构运算的候选评分写入独立临时候选，最终 Markdown 评分不取其 DOCX 权重。共享解析器新增两个可选回调：`qualification_transform(features)` 补充输入语法资格，`level_transform(feature, regime, base, proposed_level)` 使用局部 Markdown 显式锚点。DOCX 调用不传回调，原默认决策保持。

共享 schema 新增 PART，支持篇、部分、单元与章、节的外层关系。DOCX 的既有编号提取不新增 PART 规则，因此既有 DOCX 路线不改变编号语义。旧结构模块路径继续导出同一实现，避免调用方迁移和重复维护。

## 三阶段共同决定角色和有效层级

1. 局部候选：解析块范围并保留原切片；代码、引用、真实列表、表格和脚注受语法保护。编号只建立候选，不立即确定级别。长度和动作词分强弱证据，取消 35 字绝对门槛；完整操作句和句末标点仍提供正文证据。
2. 全文结构：以章、篇、附录及明确顶层容器建立局部范围，调用共享序列、章节模型、标题树与源结构恢复。边界位于新章节之前，不能抹掉前一标题已拥有的正文。显式锚点只影响本范围，不再使用全篇唯一 decimal offset。无子正文的平行编号不能仅因题名存在或家族重复而升格。
3. 最终决策：根据输入原始候选与有效树共同确定角色。已确认的缺失编号父标题自动恢复，虚拟父节点仅存在于审计，不写出标题。源编号与显式大纲序列确实互相矛盾时保留源语法并记录冲突。中等强度但结构证据成立的候选继续自动应用。

输出记录 raw/context 加减分、角色竞争、分差、源行号、前后格式、节点/父节点、Regime、结构缺陷和理由；分数表示启发式强度，不是概率。运行后的 `output-verification.json` 读取实际 DOCX 样式和有效大纲，按请求样式包编译独立参照核对段落缩进、间距和普通文字字体。局部强调、代码及脚注字符样式仍保留；不把输出自己的样式定义当作期望格式。

## 规范化版本标记保证重跑稳定

新输出的 Front Matter 标记为 `normalized-md/v2`。从该版本输出再次规范化时，已经解析的显式层级作为锚点，不重新把后来生成的同级 Markdown 标记解释为源文件展平。渲染器继续接受 v1/v2；无版本标记及 v1 输入仍进行完整新结构分析。评分和转换均保持无云端模型依赖。

稀疏中文家族按真实激活层级压缩：只有 `（一）→1.→（1）` 时可为 H1→H2→H3，不为未出现的“一、”制造父级。标准代码是保留文本，不额外制造一个标题父层。相应旧 Markdown 固定级别断言已更新；既有 230 项评估基线仍保留且通过。

## 导入修复保持正文和元数据完整

真实 DOC 链路另发现并修复了三类问题：LibreOffice 写出的合法 `start/end` 对齐值不应触发 python-docx 枚举异常；Pandoc 非 standalone 导出省略原生 Title 时，应从原件回收题名；DOC 导出的 `1\.` 编号必须在片段拼接前识别为结构起点，防止标题与其短正文合并。副标题后的作者姓名也不再被当作跨页残句拼接。

架构和质量证据见 [质量评估报告](markdown-quality-v2-repair-coverage.md)，Windows 环境验证见 [Windows Docker 说明](windows-docker-v2-startup-verification.md)。
