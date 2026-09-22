# DOCX Direct Effective Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Keep each task independently testable and commit each green stage.

**Goal:** 在 experiment/docx-direct-normalizer 分支中增加 Word 有效格式解析、保守标题/元数据/区域分类和可解释审计，同时保持 DOCX 原结构与现有写回边界不变。

**Architecture:** 新增只读 EffectiveFormatResolver，从 styles.xml 解析 docDefaults、basedOn、段落/字符样式和直接格式，向 ElementAnalysis 提供 effective_format 与 signals。Analyzer 只挂载证据，Classifier 依据证据和上下文生成既有 role/confidence/action/reasons；Mapper、Formatting 的写回职责不变，Audit 序列化完整证据。

**Tech Stack:** Python 3.12、Pydantic 2、python-docx OOXML、pytest、Ruff、Mypy、zipfile。

**Spec:** docs/superpowers/specs/2026-09-22-docx-direct-effective-format-design.md

## Global Constraints

- role 是唯一业务角色结论；effective_format 和 signals 只能保存解析证据。
- effective_format.py 只负责只读解析和生成分类证据，不参与任何 OOXML 写回。
- 有效格式继承顺序固定为 docDefaults → basedOn 父样式链 → 当前段落样式 → 当前字符样式 → 段落/运行直接格式。
- 找不到属性返回 None，不得猜测 Word 默认字体、字号或对齐方式；basedOn 必须有循环检测和最大深度。
- 东亚字体优先级固定为 eastAsia → hAnsi → ascii → cs。
- 标题识别主要使用 dominant_font_size_pt，按非空文字字符数加权；max_font_size_pt 只用于诊断。
- 上下标运行不参与主要 dominant 字号统计，但其有效格式必须保留在审计证据中。
- outlineLvl 是强证据但不是绝对判定条件，必须结合表格、自动列表、段落长度和正文句特征排除反例。
- 显式日期/作者/单位标签可以高置信映射；无标签纯姓名和无标签机构名不得为了覆盖率强判。
- 只允许高置信 mapped 元素进入现有 Style Mapper；uncertain 和 preserved 不得修改段落样式。
- 不改变段落、表格、图片、编号、超链接、域、分页符、Tab、脚注、尾注、修订、Bookmark、公式、合并单元格或嵌套表格的写回策略。
- 不修改 style_mapper.py 和 formatting.py 的职责边界。
- 不扩展到 API/UI、DOC→DOCX、LibreOffice、页面边距、分栏、Section、页眉页脚、图片尺寸、表格/编号/脚注重建、OCR、AI/LLM 或复杂公式解析。
- 每个阶段遵循 TDD：先写一个会因缺少目标行为而失败的测试，确认失败原因，再写最小实现，最后跑阶段回归。
- 不把 .codegraph/ 或运行时缓存加入提交。

## Review Focus

- 混合字号段落：正文中一个 30pt 运行不能代表整段字号；由 Task 1 的 dominant 加权测试固定。
- 上下标/局部符号：上下标字号、脚注标记或化学式不能污染 dominant 字号；由 Task 1 的运行统计测试固定。
- 自定义继承样式：自定义样式基于 Heading 继承属性不能直接成为 Heading 角色；由 Task 3 的 Classifier 回归固定。
- 日期上下文：同一日期格式在文前可成为 date，在正文只能保持正文角色；由 Task 3 的 metadata 测试固定。
- outline 反例：outlineLvl 出现在表格、自动列表、长正文或完整句时不能强制升格；由 Task 3 的 outline/region 测试固定。

---

### Task 1: Effective Formatting 回归测试与 Resolver

**Files:**
- Create: src/doc_converter/docx_direct/effective_format.py
- Create: tests/test_docx_direct_effective_formatting.py

**Interfaces:**
- Produces EffectiveFormatResolver.from_styles_xml(payload: bytes, *, max_depth: int = 32) -> EffectiveFormatResolver。
- Produces EffectiveFormatResolver.empty() -> EffectiveFormatResolver for a package without styles.xml; it returns empty evidence without default guesses。
- Produces EffectiveFormatResolver.resolve_paragraph(paragraph: Any, *, paragraph_style_id: str | None) -> dict[str, Any]。
- The returned dictionary includes paragraph properties, run statistics, dominant_font_size_pt, dominant_font_size_ratio, max_font_size_pt, dominant_bold, font fallback evidence, and style-chain evidence. It never mutates the input XML nodes.

- [ ] **Step 1: 写最小失败测试，先固定 Resolver 契约**

在 tests/test_docx_direct_effective_formatting.py 中定义 make_docx_with_styles、styles_with_style、read_member、read_document_xml 和 first_paragraph 辅助函数：用 python-docx 创建正文段落，再用 zipfile 替换 word/styles.xml 和 word/document.xml 中的最小 XML 片段。测试必须通过真实 w:docDefaults、w:style、w:basedOn、w:pStyle、w:rStyle、w:rPr 节点构造场景，不把样式继承逻辑写进测试假设。

先写以下测试：

    def test_resolver_inherits_size_and_alignment_from_paragraph_style(tmp_path):
        source = make_docx_with_styles(
            tmp_path,
            styles_xml=styles_with_style('TitleInherited', size='44', alignment='center'),
            paragraph_style='TitleInherited',
            text='继承格式标题',
        )
        paragraph = first_paragraph(read_document_xml(source))
        resolver = EffectiveFormatResolver.from_styles_xml(
            read_member(source, 'word/styles.xml')
        )

        result = resolver.resolve_paragraph(
            paragraph,
            paragraph_style_id='TitleInherited',
        )

        assert result['font_size_pt'] == 22
        assert result['alignment'] == 'center'

再增加以下独立行为测试：

- basedOn 链从自定义样式到 Heading2 可取得字号、对齐和 outline_level，但 Resolver 只返回证据；
- basedOn 循环在 max_depth=4 内终止，未取得属性为 None，不抛出递归错误；
- eastAsia 字体优先于 hAnsi、ascii，缺失时再依次回退；
- 12pt 正文加一个 30pt 单字符运行时，dominant_font_size_pt 为 12 且 dominant_font_size_ratio 小于 1；
- 12pt 正文加一个 30pt superscript 运行时，dominant 字号仍为 12，运行统计仍保留该 superscript；
- max_font_size_pt 可以为 30，但不能成为 Resolver 的主要标题结论。

- [ ] **Step 2: 运行测试确认失败且失败原因正确**

运行：

    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_effective_formatting.py

预期：因 effective_format.py 和 EffectiveFormatResolver 尚不存在而失败；若出现 XML 构造错误，先修复测试夹具，不能以跳过测试代替红灯。

- [ ] **Step 3: 实现最小只读 Resolver**

在 effective_format.py 中实现：

1. from_styles_xml 解析 w:docDefaults、所有 w:style、w:basedOn、段落/字符样式类型和 styleId；
2. 用访问集合加 max_depth 从父样式到子样式合并属性，后级覆盖前级；
3. 分别合并段落 pPr 和运行 rPr；运行解析顺序为段落样式 rPr、运行 w:rStyle 字符样式链、运行直接 w:rPr；
4. 读取 alignment、outlineLvl、keepNext、pageBreakBefore、字体、字号、粗体、斜体、颜色和 vertAlign；
5. 对 w:rFonts 按 eastAsia、hAnsi、ascii、cs 回退；
6. 按非空文字字符数计算 dominant 字号和 dominant 粗体，排除 superscript/subscript 运行的主要字号权重；
7. 把 style chain、是否存在继承 Heading 证据、每个运行的字符数和有效属性放入返回字典中的 run_statistics 或证据字段。

解析器不得调用 Document.save()，不得写临时 DOCX，不得修改传入的 lxml 节点。

- [ ] **Step 4: 运行 Resolver 测试并确认通过**

运行：

    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_effective_formatting.py
    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_effective_formatting.py tests/test_docx_direct_model.py

确认继承、字体优先级、循环保护、局部大字号和上下标测试全部通过。

- [ ] **Step 5: 提交 Effective Formatting 阶段**

    git add -- src/doc_converter/docx_direct/effective_format.py tests/test_docx_direct_effective_formatting.py
    git commit -m 'feat: resolve effective docx formatting evidence'

### Task 2: 扩展 ElementAnalysis 并接入 Analyzer

**Files:**
- Modify: src/doc_converter/docx_direct/model.py:14-38
- Modify: src/doc_converter/docx_direct/analyzer.py:32-188
- Modify: tests/test_docx_direct_model.py
- Modify: tests/test_docx_direct_analyzer.py

**Interfaces:**
- Consumes EffectiveFormatResolver from Task 1。
- Produces ElementAnalysis.effective_format: dict[str, Any] and ElementAnalysis.signals: dict[str, Any] with empty-dict defaults。
- Keeps analyze_docx(source_path: Path) -> DocumentAnalysis unchanged for all callers。

- [ ] **Step 1: 写 Analyzer/模型失败测试**

在 tests/test_docx_direct_model.py 增加 JSON round-trip 断言：构造 ElementAnalysis 时传入 effective_format 和 signals，经过 model_dump()、model_validate() 后值保持不变；不传两个字段时得到空字典。

在 tests/test_docx_direct_analyzer.py 增加一个最小 DOCX 测试：段落自身没有 w:sz 和 w:jc，但 styles.xml 的当前段落样式提供 22pt 和 center。断言：

    item = next(
        item for item in analyze_docx(source).elements
        if item.text == '继承格式标题'
    )
    assert item.effective_format['font_size_pt'] == 22
    assert item.effective_format['alignment'] == 'center'
    assert item.paragraph_properties.get('alignment') is None
    assert item.effective_format['outline_level'] is None
    assert item.signals['style_chain'] == ['TitleInherited']

同时保留压力测试中 xml_path 唯一、表格上下文、源 SHA-256 不变和原始 paragraph_properties / run_properties 断言。

- [ ] **Step 2: 运行 Analyzer 测试确认失败**

    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_model.py tests/test_docx_direct_analyzer.py

预期：模型缺少新字段或 Analyzer 没有挂载 Resolver 结果，出现明确的属性/断言失败。

- [ ] **Step 3: 扩展模型并保持默认兼容**

在 ElementAnalysis 中紧邻原始证据字段后增加：

    effective_format: dict[str, Any] = Field(default_factory=dict)
    signals: dict[str, Any] = Field(default_factory=dict)

不改变 role、confidence、action、reasons 的类型和默认值。

- [ ] **Step 4: 接入 Analyzer 的只读 Resolver**

在 analyze_docx 读取 ZIP 时同时读取可选的 word/styles.xml；存在时创建一次 EffectiveFormatResolver.from_styles_xml，不存在时使用返回空证据的 Resolver。向 _analyze_paragraph 传入 Resolver，在构造 ElementAnalysis 时：

- 保留现有直接 paragraph_properties、run_properties、numbering_properties 原样；
- 把 Resolver 返回的有效格式放入 effective_format；
- 把 style chain、继承 Heading 证据和有效格式缺失情况放入 signals；
- 不改变 _iter_paragraphs、xml_path、表格递归和任何写回代码。

- [ ] **Step 5: 运行 Analyzer 和 Direct 既有测试**

    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_model.py tests/test_docx_direct_analyzer.py tests/test_docx_direct_mapping.py

确认 Mapper 仍只依据 role/action，新字段不会改变现有目标样式和列表保留结果。

- [ ] **Step 6: 提交 Analyzer 阶段**

    git add -- src/doc_converter/docx_direct/model.py src/doc_converter/docx_direct/analyzer.py tests/test_docx_direct_model.py tests/test_docx_direct_analyzer.py
    git commit -m 'feat: attach effective formatting to docx analysis'

### Task 3: 改进 Classifier、元数据和区域边界

**Files:**
- Modify: src/doc_converter/docx_direct/classifier.py:37-278
- Modify: tests/test_docx_direct_classifier.py
- Create: tests/test_docx_direct_metadata.py
- Create: tests/test_docx_direct_regions.py

**Interfaces:**
- Consumes ElementAnalysis.effective_format and ElementAnalysis.signals from Task 2。
- Produces the existing classify_document(analysis: DocumentAnalysis) -> DocumentAnalysis contract。
- Does not change style_mapper.py or formatting.py。

- [ ] **Step 1: 写 Classifier 失败测试**

在现有分类测试中增加以下断言：

    def test_outline_level_is_strong_but_not_absolute():
        by_text = classified_generated_fixture()
        assert by_text['2 适用范围'].role == 'heading-1'
        assert by_text['表格中的普通正文'].role == 'body-table'
        assert (
            by_text[
                '这是一个很长的正文句子，包含完整说明并以句号结束。'
            ].role
            != 'heading-1'
        )

    def test_custom_style_based_on_heading_is_not_automatically_a_heading():
        item = classified_generated_fixture()['自定义样式正文句']
        assert item.role not in {'heading-1', 'heading-2', 'heading-3'}
        assert item.action in {'uncertain', 'preserved'}
        assert item.signals['based_on_heading'] is True

在 tests/test_docx_direct_metadata.py 构造文前标题、作者标签、单位标签、日期和正文日期，断言显式标签/文前日期映射，正文日期不映射为 date，无标签 张三 和无标签机构名不产生 mapped。

在 tests/test_docx_direct_regions.py 构造标题、副标题、作者、单位、摘要、关键词、outline 标题、正文、参考文献和条目，断言：

    assert title.region == 'preface'
    assert subtitle.region == 'preface'
    assert heading.region == 'body'
    assert body.region == 'body'
    assert reference_heading.region == 'postface'
    assert entry.region == 'postface'
    assert title.text != subtitle.text

另外固定局部 30pt 字符、superscript 字符、自动列表和表格普通文本不升格为标题。

- [ ] **Step 2: 运行 Classifier 测试确认失败**

    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_classifier.py tests/test_docx_direct_metadata.py tests/test_docx_direct_regions.py

预期：现有代码会因只读直接格式、未使用 outline、缺少元数据规则或区域边界错误而失败；先确认失败来自缺少目标行为，不放宽断言。

- [ ] **Step 3: 把分类辅助函数切换到有效格式**

将 _alignment 改为优先读取 element.effective_format['alignment']；将 _font_size_pt 改为读取 dominant_font_size_pt，并在 dominant 覆盖率不足时返回 None。保留直接属性作为兼容回退，但不得再用任意 run 的 max() 驱动标题判断。

新增 _outline_heading_level(element)：读取有效 outline_level，映射 0→1 至 5→6，但对表格、自动列表、过长文本、完整正文句、复杂对象和低 dominant 覆盖率返回 None。该函数只产生证据，最终角色仍由分类流程决定。

- [ ] **Step 4: 调整区域和标题/副标题分类**

让 _assign_regions 使用经过排除条件校验的原生 Heading、outline 标题或高置信编号标题启动 body；参考文献边界之后保持 postface。让 _classify_title_area 使用有效对齐、dominant 字号和 dominant 覆盖率，排除摘要、关键词、日期、作者、单位和部门；副标题只选标题之后紧邻的独立元素。

保留每个原始段落的 document_order、xml_path 和文本，不合并标题副标题，不拆软换行。

- [ ] **Step 5: 增加高确定性元数据规则**

按分类顺序在普通正文规则前处理：

- 作者：、编制：、编写：后的短文本映射 author；
- 单位：、部门：、编制单位：后的短文本映射 organization-department；
- 明确日期格式仅在 preface 且位于标题/副标题之后的文前上下文映射 date；
- 无标签纯姓名保持 unknown/preserved；无标签机构后缀最多形成 organization-department/uncertain，不得 mapped；
- 正文中的日期、作者样式文本和机构样式文本按正文上下文处理。

每个决定追加可读 reasons，并把 date_pattern、metadata_label、based_on_heading、outline_heading、automatic_list、body_sentence 等放入 signals，不新增业务结论字段。

- [ ] **Step 6: 运行分类和现有映射测试**

    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_classifier.py tests/test_docx_direct_metadata.py tests/test_docx_direct_regions.py tests/test_docx_direct_mapping.py

确认原有 Heading 1–6、人工编号标题、列表保留、题注和表格正文测试全部通过，并人工查看生成元素的 role/action 计数。

- [ ] **Step 7: 提交 Classifier 阶段**

    git add -- src/doc_converter/docx_direct/classifier.py tests/test_docx_direct_classifier.py tests/test_docx_direct_metadata.py tests/test_docx_direct_regions.py
    git commit -m 'feat: classify docx roles from effective evidence'

### Task 4: 补强 Audit 输出并验证 Normalizer 集成

**Files:**
- Modify: src/doc_converter/docx_direct/audit.py:50-86
- Create: tests/test_docx_direct_audit.py
- Modify: tests/test_docx_direct_normalizer.py

**Interfaces:**
- Consumes the classified DocumentAnalysis from Task 3。
- Keeps write_audit_bundle(...) and DirectNormalizeResult public call shapes compatible。
- Produces docx-analysis.json containing original evidence, effective_format, signals, role, confidence, action and reasons for every element。

- [ ] **Step 1: 写 Audit 失败测试**

调用现有 normalize_docx_direct 处理最小继承格式 DOCX，读取 docx-analysis.json，固定以下断言：

    payload = json.loads(analysis_path.read_text(encoding='utf-8'))
    item = next(
        item for item in payload['elements']
        if item['text'] == '继承格式标题'
    )
    assert item['paragraph_properties'] == {}
    assert item['effective_format']['font_size_pt'] == 22
    assert item['signals']['style_chain'] == ['TitleInherited']
    assert item['role'] == 'document-title'
    assert item['action'] == 'mapped'
    assert item['reasons']

再固定：源文件 SHA-256 不变、规范化报告的 counts 与 records 仍一致、uncertain/preserved 元素没有 target style、三份审计文件只在成功输出时产生。

- [ ] **Step 2: 运行 Audit 测试确认失败**

    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_audit.py tests/test_docx_direct_normalizer.py

预期：模型新增字段后，分析报告的字段路径和现有审计断言尚未完整固定；先确认失败信息，再实现。

- [ ] **Step 3: 让 Audit 明确保留两层证据**

在 audit.py 中将分析 payload 构造集中到一个私有函数：先调用 analysis.model_dump(mode='json')，再确保每个 element 保留 paragraph_properties、run_properties、effective_format、signals、role、confidence、action、reasons。在报告根级增加固定的 evidence_fields 列表：

    ['paragraph_properties', 'run_properties', 'effective_format', 'signals']

不要把有效格式合并回原始直接属性，也不要把 signals 改名成 role。规范化报告继续使用现有 NormalizationRecord，不把未映射元素伪装成 target style。

- [ ] **Step 4: 运行 Audit、Normalizer 和压力测试**

    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_audit.py tests/test_docx_direct_normalizer.py tests/test_docx_direct_pressure.py

核对压力文档的源 SHA-256、输出可读性、图片数量、表格合并、关键文本顺序、numbering.xml、脚注、尾注和关系部件不变量。

- [ ] **Step 5: 提交 Audit 阶段**

    git add -- src/doc_converter/docx_direct/audit.py tests/test_docx_direct_audit.py tests/test_docx_direct_normalizer.py
    git commit -m 'feat: audit effective docx evidence'

### Task 5: 全量回归与分支级交付复核

**Files:**
- Test: tests/test_docx_direct_effective_formatting.py
- Test: tests/test_docx_direct_metadata.py
- Test: tests/test_docx_direct_regions.py
- Test: all existing tests/test_docx_direct_*.py
- Test: tests/test_importers.py, tests/test_renderer.py, tests/test_api.py

**Interfaces:**
- Consumes the four staged commits above。
- Produces fresh verification evidence and a branch-scope report；此任务不扩大功能范围。

- [ ] **Step 1: 运行 Direct 全套测试**

    .\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_*.py

必须确认 Effective Formatting、Analyzer、Classifier、Audit、Mapper、Normalizer 和压力测试全部通过。

- [ ] **Step 2: 运行主路线回归**

    .\.venv\Scripts\python.exe -m pytest -q tests/test_importers.py tests/test_renderer.py tests/test_api.py tests/test_normalizer.py

确认 Direct 证据字段没有改变 Round-trip 导入、Markdown 规范化、Renderer 或 API 的行为。

- [ ] **Step 3: 运行完整质量门禁**

    .\.venv\Scripts\python.exe -m pytest -q
    .\.venv\Scripts\python.exe -m ruff check .
    .\.venv\Scripts\python.exe -m mypy src
    git diff --check

记录每条命令的真实退出码和失败数量；不得以局部测试通过替代全量结果。若出现与本轮无关的既有失败，按测试名和输出原样记录。

- [ ] **Step 4: 检查变更范围与结构不变量**

    git status --short --branch
    git diff --name-only main...HEAD
    git log --oneline --decorate main..HEAD

确认本轮没有修改 API/UI、importers/docx.py、docx_extensions.py、style_mapper.py、formatting.py 之外的非必要范围，没有提交 .codegraph/，并且所有小提交按 Effective Formatting → Analyzer → Classifier → Audit 的顺序排列。

- [ ] **Step 5: 输出交付摘要**

报告分支名、四个阶段提交、全量测试/Ruff/Mypy/diff 结果、压力测试结构保真结果，以及明确保留到后续阶段的 API/UI、Section、图片、表格、编号和其他非目标范围。
