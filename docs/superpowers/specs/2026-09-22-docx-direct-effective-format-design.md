# DOCX Direct Effective Formatting 解读优化设计

## 1. 目标与状态

本设计用于 `experiment/docx-direct-normalizer` 分支的下一阶段迭代，目标是提升 DOCX Direct Normalizer 对 Word 实际有效格式、标题证据、文前元数据和文档区域的只读解读能力。

设计状态：已获用户确认，进入设计文档审阅阶段。

本轮仍沿用现有流水线：DOCX → Analyzer → Classifier → Style Injector → Style Mapper → Formatting → Audit + 输出 DOCX。本轮只增强前半段的 DOCX 解读能力，不把解析信号直接变成写回动作。

## 2. 不可变约束

### 2.1 业务结论只有 role、confidence、action

`role` 是唯一业务角色结论；`confidence` 和 `action` 共同决定后续是否允许样式映射。动作状态固定为 `mapped`、`uncertain`、`preserved`。

`outline_level`、字号、对齐、样式名、编号、文本模式、表格上下文以及所有新增判断结果都属于证据，不得新增与 `role` 并列的 `is_heading` 等业务结论字段。中间信号统一放入 `signals: dict[str, Any]`。

### 2.2 有效格式解析是只读能力

`effective_format.py` 只负责读取 DOCX 的样式和属性继承链，生成供分类器使用的解析证据。它不得修改源 DOCX 或任何 OOXML 节点，不参与 `word/document.xml`、`word/styles.xml` 或其他部件的写回，也不得改变现有 Style Injector、Style Mapper、Formatting 的职责边界。

现有 Mapper 仍只依据 `role`、`confidence`、`action` 及目标角色映射修改 `w:pStyle`；现有 Formatting 仍只处理明确允许接管的直接格式。

### 2.3 结构安全优先

本轮不重建段落、表格、图片、编号、超链接、域、分页符、Tab、脚注、尾注、修订、Bookmark、公式、合并单元格或嵌套表格。不引入 Markdown 中间层，不接入 API/UI，不处理 DOC、分栏、Section、页眉页脚样式、图片尺寸或表格重建。

## 3. 当前缺口与总体方案

当前 Analyzer 主要读取段落和运行的直接 `w:pPr`、`w:rPr`；Classifier 的字号判断取运行字号的最大值，区域判断主要依赖直接样式名和编号文本。这会漏掉通过 `docDefaults`、`basedOn` 或段落/字符样式继承得到的有效格式，也会把正文中的局部大字号、上下标字号或自定义继承样式误当成标题证据。

本轮新增独立的 Effective Formatting Resolver，并按以下阶段实施：

1. `effective_format.py`：解析有效格式并生成段落级统计；
2. `ElementAnalysis`：增加解析证据字段，不改变既有原始字段；
3. Analyzer：把 Resolver 结果挂载到分析模型；
4. Classifier：使用有效格式、outline 和上下文进行保守分类；
5. Audit：完整输出原始证据、解析证据和业务结论；
6. 全量 Direct、压力和主路线回归。

不把 Analyzer、Classifier、Mapper 和 Formatting 合并成一次性重写。

## 4. 数据流与模块边界

Analyzer 从同一个 DOCX ZIP 读取 `word/document.xml` 和 `word/styles.xml`，把 XML 载荷交给 Resolver，生成 `ElementAnalysis`。Classifier 只消费 `DocumentAnalysis`，不直接读取或修改 DOCX。Mapper 和 Formatting 继续消费分类结果并执行既有的最小 XML 修改。Audit 只序列化分析结果和规范化记录。

解析链为：`document.xml + styles.xml → Effective Resolver → Analyzer evidence → Classifier conclusion → existing Mapper / Formatting → Audit`。

## 5. Effective Formatting Resolver

新增模块：`src/doc_converter/docx_direct/effective_format.py`。

### 5.1 继承顺序

属性合并按以下顺序执行，后级覆盖前级：

`docDefaults → basedOn 父样式链 → 当前段落样式 → 当前字符样式 → 段落/运行直接格式`

段落属性和运行属性分别合并。段落样式中的 `pPr` 只影响段落属性，段落样式中的 `rPr` 作为该段落运行的继承基线；运行节点中的 `w:rStyle` 再叠加字符样式链，最后叠加直接 `w:rPr`。

`basedOn` 解析必须使用访问集合和最大深度保护。遇到循环、缺失父样式或不完整 `styles.xml` 时停止该链并保留已取得的属性；未取得的属性返回 `None`，不得猜测 Word 默认字号、字体或对齐方式。

### 5.2 首期属性范围

段落级至少采集 `alignment`、`outline_level`、`keep_next`、`page_break_before`；后两个只作为证据，首期不参与格式写回。

运行级至少采集 `font_name`、`font_size_pt`、`bold`、`italic`、`color`、`vert_align`。

东亚字体优先级为 `eastAsia → hAnsi → ascii → cs`。字号按 OOXML 半磅值转换为 pt，优先使用 `w:sz`，必要时读取 `w:szCs`，不根据经验补默认值。

### 5.3 段落级统计

`effective_format` 至少包含：`alignment`、`outline_level`、`font_name`、`font_size_pt`、`bold`、`italic`、`color`、`dominant_font_size_pt`、`dominant_font_size_ratio`、`max_font_size_pt`、`dominant_bold` 和 `run_statistics`。

`dominant_font_size_pt` 按各运行的非空文字字符数加权，不使用任意单个运行的最大字号作为标题判断依据。`dominant_font_size_ratio` 表示 dominant 字号覆盖的有效文字比例，用于排除单个大字号字符代表整段的误判。

带 `vertAlign=superscript` 或 `subscript` 的运行不参与主要 dominant 字号统计，以避免脚注标记、化学式和数学表达式影响整段字号；这些运行的有效格式仍保留在审计证据中。`max_font_size_pt` 仅用于诊断，不直接驱动角色分类。

如果段落只有上下标运行，或有效文字统计不足，dominant 统计返回 `None` 或低覆盖率结果，分类器按不确定处理。

## 6. ElementAnalysis 数据模型

在现有 `ElementAnalysis` 中新增 `effective_format: dict[str, Any]` 和 `signals: dict[str, Any]`，默认值为空字典以保持旧构造方式和旧测试兼容。

三层语义保持明确：

- 原始证据：`original_style_id`、`original_style_name`、`paragraph_properties`、`run_properties`、`numbering_properties`、`table_context`；
- 解析证据：`effective_format`、`signals`；
- 业务结论：`role`、`confidence`、`action`、`reasons`。

新增字段不得覆盖原始直接属性。

## 7. Classifier 设计

### 7.1 标题证据优先级

标题候选按以下顺序积累证据，而不是由单一属性直接决定 `role`：原生 Heading 1–6、有效 `outline_level`、有效对齐和 dominant 字号等视觉证据、人工编号规则、前后文和段落内容。

`outlineLvl=0` 对应 `heading-1`，`outlineLvl=1` 对应 `heading-2`，以此类推。但 `outlineLvl` 只是强证据，不是绝对条件。表格内部普通文本、自动编号或项目符号、明显过长的正文、以完整正文句标点结尾的段落、复杂对象段落以及缺乏上下文的自定义继承样式必须降级或保留。

自定义样式仅通过 `basedOn` 继承 Heading 属性时，这一事实只写入 `signals`，不能直接等同于原生 Heading 角色。

### 7.2 标题、副标题和边界

`document-title` 必须位于 `preface`，不是表格段落、非空、不是摘要/关键词/日期/作者/单位等元数据，有效对齐为居中，dominant 字号在合理文前候选中最大或显著最大，且长度合理。

`document-subtitle` 只能从标题后紧邻的文前独立段落中产生，通常居中且 dominant 字号不大于标题。标题和副标题始终保留为两个元素，不合并原始段落，也不因软换行拆段。

候选冲突使用少量可解释的评分理由，例如文前、居中、字号显著、靠近起始位置、元数据排除和正文句尾排除；最终仍只输出 `role`、`confidence`、`action`、`reasons`。

### 7.3 文前元数据

首期只采用高确定性规则：

- `date` 支持 `2026年9月`、`2026年9月22日`、`2026-09-22`、`2026.09.22`、`二〇二六年九月` 等明确格式；只有位于 `preface` 且具备文前上下文时才高置信映射，正文日期保持正文角色；
- `author` 对 `作者：`、`编制：`、`编写：` 等明确标签高置信映射，无标签纯姓名不强判；
- `organization-department` 对 `单位：`、`部门：`、`编制单位：` 等明确标签高置信映射；无标签机构名只能作为上下文证据，不能为了覆盖率强制映射。

无法可靠判断的作者或机构角色保持 `uncertain` 或 `preserved`。

### 7.4 区域

区域只保留 `preface`、`body`、`postface`。正文开始的强信号为经过排除条件校验的原生 Heading、有效 `outlineLvl` 或高置信人工编号标题。一旦正文开始，后续普通内容保持 `body`，直到遇到明确的 `参考文献`、`参考资料`、`References`，必要时再识别高确定性的 `附录`/`附件`边界。区域状态机只服务于角色分类，不构建全文语义解析器。

## 8. Audit 设计

`docx-analysis.json` 对每个元素同时输出原始样式、段落/运行直接属性、`effective_format`、`signals`、`role`、`confidence`、`action` 和 `reasons`。审计层应能区分 Analyzer 未取得有效格式和 Classifier 取得证据但未达到映射阈值。

审计不改变输出 DOCX，不扩大 XML 写入范围。

## 9. 测试设计

新增：

- `tests/test_docx_direct_effective_formatting.py`
- `tests/test_docx_direct_metadata.py`
- `tests/test_docx_direct_regions.py`

测试覆盖样式继承字号和对齐、`basedOn` 链与循环保护、东亚字体优先级、dominant 字号字符加权、正文局部大字号、上下标、单个大字号字符、自定义继承 Heading、outline 排除条件、标题副标题段落边界、显式作者/单位/日期、正文日期、区域边界以及审计字段。

现有 Direct、压力和主路线测试继续保留；不得通过修改旧预期掩盖回归。

## 10. 验收与非目标

验收顺序固定为：Effective Formatting 测试 → Analyzer / Classifier / Audit 测试 → Direct 全套 → 压力测试 → 主路线回归 → Ruff / Mypy / `git diff --check`。

压力测试继续验证 `numbering.xml`、脚注、尾注、关系、图片数量、表格合并、嵌套表格和关键文本顺序等结构不变量，源文件 SHA-256 必须不变。

本轮不实现 API/UI 接入、DOC→DOCX、LibreOffice 调用、页面边距、分栏、Section、页眉页脚样式、图片尺寸、表格重建、编号重建、脚注/尾注重建、OCR、AI/LLM 分类和复杂公式解析。
