# DOCX Direct Normalizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 在 experiment/docx-direct-normalizer 分支实现并验证 DOCX → DOCX 原位规范化核心路线，同时保持现有 Markdown Round-trip 路线不变。

**Architecture:** 新增 src/doc_converter/docx_direct/ 独立模块。Analyzer 通过原始 word/document.xml 的真实节点顺序建立可序列化分析模型，Classifier 只把高置信内容映射到既有 Style Pack 角色；Normalizer 复制 DOCX ZIP 后仅增量写入 word/styles.xml 和必要的 word/document.xml 段落样式/允许清理的运行属性，所有其他 OOXML 部件原样复制。

**Tech Stack:** Python 3.12、python-docx 的现有 OOXML 层、zipfile、Pydantic 2、pytest、现有 StylePack/compile_styles()。

**Spec:** docs/superpowers/specs/2026-09-22-docx-direct-normalizer-design.md

## Global Constraints

- main 保留当前 DOCX → Markdown → DOCX Round-trip 实现；不得删除、覆盖或大规模重构。
- 实验分支固定为 experiment/docx-direct-normalizer，且不得合并到 main。
- Direct 路线不得调用 Pandoc、LibreOffice、现有 Markdown importer，也不得伪造 Markdown draft。
- 原始上传文件绝不修改；源路径与输出路径相同必须拒绝；失败时不得留下半成品输出。
- 只新增缺失的 DC_* 样式，不替换整个 word/styles.xml，不覆盖原有同名样式。
- w:numPr、超链接、Tab、手动/分页符、图片、域、修订、上下标、脚注/尾注、关系、分节、表格合并和嵌套表格不得被重建。
- 分类动作阈值固定为：mapped >= 0.90、uncertain 0.70–<0.90、preserved <0.70；uncertain 不修改段落。
- 第一版只处理主文档正文及表格单元格内普通段落；页眉页脚、页面/分节设置、DOC、API/UI 不在本计划范围内。
- 自动列表和带 w:numPr 的段落默认保留，以保证列表语义；普通编号标题只有在符合高置信规则时才升格。
- 用户提供的 C:\Users\Lenovo\Downloads\DOCX转Markdown压力测试_V1_结构兼容性.docx 固化为仓库测试夹具；不得修改 Downloads 中的原文件。

## Review Focus

- 标题与副标题为相邻但独立的段落，或同一段中的软换行时，识别不能错误合并/拆分；由 Task 3 的 title-area tests 固定。
- 普通编号正文、真正的自动列表和编号式标题同时出现时，不能把列表或正文句错误升格；由 Task 3 的 numbering/list tests 固定。
- 全段一致的直接字体格式可以移交给目标样式，但局部粗体/斜体、上下标、Tab、分页符和超链接必须保留；由 Task 5 的 OOXML tests 固定。
- 合并表格、纵向合并、嵌套表格、图片关系、脚注/尾注和修订部件必须保持；由 Task 6 的 package-invariant tests 固定。
- 解析失败、源输出同路径和中途写入失败不能破坏源文件或产生误导性审计报告；由 Task 6 的 atomic-output tests 固定。

---

### Task 1: 固化压力测试夹具并建立 Direct 数据模型

**Files:**
- Create: tests/fixtures/DOCX转Markdown压力测试_V1_结构兼容性.docx（从用户提供文件复制的二进制夹具）
- Create: src/doc_converter/docx_direct/__init__.py
- Create: src/doc_converter/docx_direct/model.py
- Test: tests/test_docx_direct_model.py

**Interfaces:**
- Consumes: 现有 StylePack，以及用户提供的压力测试 DOCX。
- Produces: ElementAnalysis、DocumentAnalysis、NormalizationRecord、DirectNormalizeResult，供后续 Analyzer、Classifier、Patch 和 Audit 使用。

- [ ] **Step 1: 固化用户提供的测试文件并写夹具完整性测试**

将文件复制到仓库夹具目录，并记录源/夹具 SHA-256：

~~~powershell
Copy-Item -LiteralPath 'C:\Users\Lenovo\Downloads\DOCX转Markdown压力测试_V1_结构兼容性.docx' -Destination 'tests\fixtures\DOCX转Markdown压力测试_V1_结构兼容性.docx'
~~~

新增测试：

~~~python
def test_pressure_fixture_is_the_user_provided_docx():
    source = Path(r"C:\Users\Lenovo\Downloads\DOCX转Markdown压力测试_V1_结构兼容性.docx")
    fixture = Path(__file__).parent / "fixtures" / source.name
    assert fixture.is_file()
    assert sha256(source) == sha256(fixture)
~~~

当 Downloads 文件不可用时，测试应明确失败并提示缺少用户指定夹具，而不是静默跳过。

- [ ] **Step 2: 运行测试确认夹具测试失败或通过于正确原因**

运行：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_model.py::test_pressure_fixture_is_the_user_provided_docx
~~~

预期：复制前为明确的 fixture 缺失失败；复制后为 PASS。

- [ ] **Step 3: 写出模型测试**

模型使用 Pydantic，字段至少覆盖：

~~~python
class ElementAnalysis(BaseModel):
    element_id: str
    element_type: Literal["paragraph"]
    text: str
    document_order: int
    xml_path: tuple[int, ...]
    region: Literal["preface", "body", "postface"]
    original_style_id: str | None = None
    original_style_name: str | None = None
    paragraph_properties: dict[str, Any] = Field(default_factory=dict)
    run_properties: list[dict[str, Any]] = Field(default_factory=list)
    numbering_properties: dict[str, Any] = Field(default_factory=dict)
    table_context: dict[str, Any] | None = None
    role: str = "unknown"
    confidence: float = 0.0
    action: Literal["mapped", "uncertain", "preserved"] = "preserved"
    reasons: list[str] = Field(default_factory=list)
~~~

DocumentAnalysis 还要记录 source_sha256、elements、package_entries、main_document_stats；NormalizationRecord 要能表达 mapped、uncertain 和 preserved；DirectNormalizeResult 要包含四个产物路径和分析对象。测试必须验证模型可以 model_dump()/model_validate() 往返，置信度范围为 0–1，并且 action 只接受 mapped、uncertain、preserved。

- [ ] **Step 4: 运行模型测试确认失败**

运行：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_model.py
~~~

预期：在模型未定义时因导入/属性缺失失败，而不是测试语法错误。

- [ ] **Step 5: 实现最小模型和公共导出**

在 model.py 实现上述模型，在 __init__.py 导出公共模型名。不要在此任务中实现 XML 解析或规范化行为。

- [ ] **Step 6: 运行任务测试并提交**

运行：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_model.py
~~~

预期：夹具完整性和模型测试全部通过。提交：

~~~powershell
git add tests/fixtures/DOCX转Markdown压力测试_V1_结构兼容性.docx src/doc_converter/docx_direct tests/test_docx_direct_model.py
git commit -m "feat: add docx direct analysis models"
~~~

### Task 2: 实现只读 Analyzer

**Files:**
- Create: src/doc_converter/docx_direct/analyzer.py
- Modify: src/doc_converter/docx_direct/__init__.py
- Test: tests/test_docx_direct_analyzer.py

**Interfaces:**
- Consumes: Path 指向有效 DOCX；Task 1 的 DocumentAnalysis/ElementAnalysis。
- Produces: analyze_docx(source_path: Path) -> DocumentAnalysis；纯读操作，不生成或修改任何文件。

- [ ] **Step 1: 写 Analyzer 的失败测试**

测试以下行为：

~~~python
def test_analyzer_reports_pressure_document_without_writing_source():
    source = fixture_path()
    before = sha256(source)
    result = analyze_docx(source)

    assert result.source_sha256 == before
    assert len(result.elements) > 86
    assert result.main_document_stats["tables"] == 4
    assert result.main_document_stats["sections"] == 3
    assert result.main_document_stats["inline_shapes"] == 3
    assert any(item.text == "CASE-H-001 标题层级与正文结构" for item in result.elements)
    assert any(item.table_context for item in result.elements)
    assert sha256(source) == before
~~~

另测无效 ZIP、缺失 word/document.xml 和空正文的错误信息。测试应检查分析结果中的 xml_path 能唯一定位重复文本段落。

- [ ] **Step 2: 运行 Analyzer 测试确认失败**

运行：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_analyzer.py
~~~

预期：因 analyze_docx 尚不存在而失败。

- [ ] **Step 3: 实现只读 ZIP/XML 遍历**

使用 zipfile.ZipFile 读取 word/document.xml，使用现有 python-docx OOXML 层和 qn 解析节点，不调用 Document.save()。按 w:body 子节点递归遍历段落和表格，给每个段落生成 p-0001 形式 ID、真实子节点路径和文档顺序。

提取：

~~~text
w:pPr/w:pStyle
w:pPr/w:jc、w:ind、w:spacing、w:numPr
w:rPr/w:rFonts、w:sz、w:b、w:i、w:color、w:vertAlign
w:hyperlink、w:tab、w:br、w:drawing、w:fldSimple、w:ins、w:del
表格层级、行列索引、是否嵌套表格
~~~

通过 python-docx 的只读对象读取样式名、分节数和图片数量；如需 XML 细节，以 ZIP 中的 XML 为准。计算源 SHA-256 和包成员清单，不写入分析产物。

- [ ] **Step 4: 运行 Analyzer 测试确认通过**

运行同一命令，预期压力文件统计、锚点和源不变测试全部通过；再运行现有回归：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_analyzer.py tests/test_importers.py
~~~

- [ ] **Step 5: 提交 Analyzer**

~~~powershell
git add src/doc_converter/docx_direct/analyzer.py src/doc_converter/docx_direct/__init__.py tests/test_docx_direct_analyzer.py
git commit -m "feat: analyze docx structure without rewriting"
~~~

### Task 3: 实现区域识别和角色分类

**Files:**
- Create: src/doc_converter/docx_direct/classifier.py
- Modify: src/doc_converter/docx_direct/model.py
- Modify: src/doc_converter/docx_direct/__init__.py
- Test: tests/test_docx_direct_classifier.py

**Interfaces:**
- Consumes: Task 2 的 DocumentAnalysis，以及现有 StylePack.roles。
- Produces: classify_document(analysis: DocumentAnalysis) -> DocumentAnalysis，返回带 role、confidence、reasons 的新分析对象；不修改源 DOCX。

- [ ] **Step 1: 写分类失败测试**

至少固定以下断言：

~~~python
def test_classifier_maps_native_headings_and_keeps_lists_preserved():
    analysis = classify_document(analyze_docx(fixture_path()))
    by_text = {item.text: item for item in analysis.elements}

    assert by_text["CASE-H-001 标题层级与正文结构"].role == "heading-1"
    assert by_text["CASE-H2-002 Heading 2 中文标题"].role == "heading-2"
    assert by_text["CASE-H6-006 Heading 6 中文标题"].role == "heading-6"
    assert by_text["CASE-LIST-B1 一级项目符号 A"].role == "unknown"
    assert "列表" in "".join(by_text["CASE-LIST-B1 一级项目符号 A"].reasons)

def test_classifier_recognizes_numbered_heading_but_not_numbered_sentence():
    analysis = classify_document(analyze_docx(fixture_path()))
    by_text = {item.text: item for item in analysis.elements}

    assert by_text["一、一级中文编号但使用普通正文样式 〔CASE-MANUAL-001〕"].role == "heading-1"
    assert by_text["（一）二级中文编号但使用普通正文样式 〔CASE-MANUAL-002〕"].role == "heading-2"
    assert by_text["CASE-LIST-LITERAL-001 1. 这行看起来像编号，但只是普通正文中的字面文本。"].role == "unknown"

def test_classifier_keeps_title_and_subtitle_as_separate_elements():
    analysis = classify_document(analyze_docx(fixture_path()))
    roles = [(item.text, item.role) for item in analysis.elements if item.role in {"document-title", "document-subtitle"}]
    assert roles[:2] == [
        ("DOCX → Markdown 转换压力测试文档", "document-title"),
        ("V1 · 结构兼容性 / 边界场景 / 可定位验收", "document-subtitle"),
    ]
~~~

再补充参考文献边界、表格正文、表题/图题、普通正文、结尾标点禁止升格和 mapped/uncertain/preserved 阈值测试。

- [ ] **Step 2: 运行分类测试确认失败**

运行：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_classifier.py
~~~

预期：因分类入口或规则尚不存在失败。

- [ ] **Step 3: 实现确定性分类器**

按规范中的优先级实现：原生 Heading/outline、文前标题副标题、显式元数据、编号启发式、参考文献边界、表格上下文、题注和普通正文。每条规则追加可读中文理由；不满足高置信条件时保留 unknown 并根据阈值生成 action，不把自动列表映射成正文样式。action 与 role/confidence 一起写回 ElementAnalysis。

- [ ] **Step 4: 运行分类测试并检查结果**

运行：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_classifier.py
~~~

预期全部通过，并打印一次压力文档角色计数用于人工核对。若规则与规范冲突，先补测试再改规则。

- [ ] **Step 5: 提交分类器**

~~~powershell
git add src/doc_converter/docx_direct/model.py src/doc_converter/docx_direct/classifier.py src/doc_converter/docx_direct/__init__.py tests/test_docx_direct_classifier.py
git commit -m "feat: classify docx semantic roles conservatively"
~~~

### Task 4: 增量注入 DC_* 样式并建立 ZIP/XML 写回基础

**Files:**
- Create: src/doc_converter/docx_direct/style_injector.py
- Create: src/doc_converter/docx_direct/ooxml_patch.py
- Modify: src/doc_converter/docx_direct/__init__.py
- Test: tests/test_docx_direct_style_injector.py

**Interfaces:**
- Consumes: StylePack、有效 DOCX ZIP。
- Produces: inject_styles_into_docx(source_path: Path, style_pack: StylePack, output_path: Path) -> dict[str, Any]；以及 XML payload 读写辅助函数，供 Task 5/6 使用。

- [ ] **Step 1: 写增量注入失败测试**

测试先构造一个含 Normal、Heading 1 和自定义样式的 DOCX，调用注入后检查：

~~~python
def test_style_injection_adds_dc_styles_without_replacing_existing_styles(tmp_path):
    source = make_source_docx(tmp_path)
    output = tmp_path / "injected.docx"
    report = inject_styles_into_docx(source, create_style_pack(name="test", format_id="docx"), output)

    original_ids = read_style_ids(source)
    output_ids = read_style_ids(output)
    assert original_ids <= output_ids
    assert {"DC_DocumentTitle", "DC_Heading1", "DC_BodyParagraph"} <= output_ids
    assert report["inserted_count"] > 0
~~~

再运行一次注入，验证同名 DC_* 不重复、不被覆盖。比较 word/document.xml、图片、关系、编号和尾注 payload，确认注入只改 word/styles.xml。

- [ ] **Step 2: 运行测试确认失败**

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_style_injector.py
~~~

预期：因注入入口不存在失败。

- [ ] **Step 3: 实现样式模板提取和增量插入**

复用 doc_converter.docx_styles.compile_styles() 在临时 Document() 中编译角色；只提取 ROLE_TO_STYLE_ID 对应的 w:style 元素。读取原 word/styles.xml，保留所有现有节点，在合法的 style 节点区域插入缺失样式；不复制临时文档的 docDefaults、页面设置、编号或关系。

在 ooxml_patch.py 实现：

~~~python
read_zip_member(source_path: Path, member: str) -> bytes
write_zip_copy(source_path: Path, output_path: Path, replacements: Mapping[str, bytes]) -> None
~~~

写包时复制所有未替换成员的原始 payload，目标写入临时文件后再由调用方原子移动。

- [ ] **Step 4: 运行样式注入和全套既有测试**

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_style_injector.py tests/test_style_library.py tests/test_renderer.py
~~~

预期全部通过，现有 renderer/style library 行为不得改变。

- [ ] **Step 5: 提交样式注入基础**

~~~powershell
git add src/doc_converter/docx_direct/style_injector.py src/doc_converter/docx_direct/ooxml_patch.py src/doc_converter/docx_direct/__init__.py tests/test_docx_direct_style_injector.py
git commit -m "feat: inject direct docx styles incrementally"
~~~

### Task 5: 实现段落样式映射和保守 Direct Formatting 清理

**Files:**
- Create: src/doc_converter/docx_direct/style_mapper.py
- Create: src/doc_converter/docx_direct/formatting.py
- Modify: src/doc_converter/docx_direct/ooxml_patch.py
- Modify: src/doc_converter/docx_direct/__init__.py
- Test: tests/test_docx_direct_mapping.py

**Interfaces:**
- Consumes: Task 3 的已分类 DocumentAnalysis，Task 4 的 word/document.xml payload。
- Produces: patch_document_xml(payload: bytes, analysis: DocumentAnalysis) -> tuple[bytes, dict[str, Any]]；只对 mapped 段落设置目标 w:pStyle，并对全段一致的允许属性执行清理。

- [ ] **Step 1: 写 XML 映射失败测试**

使用最小 DOCX/原始 XML 固定：

~~~python
def test_mapping_changes_only_mapped_paragraph_styles():
    before = read_member(source, "word/document.xml")
    after, report = patch_document_xml(before, classified_analysis)

    assert paragraph_style(after, "CASE-H-001") == "DC_Heading1"
    assert paragraph_style(after, "CASE-LIST-B1") == "ListBullet"
    assert numbering_payload(before) == numbering_payload(after)
    assert report["mapped_count"] >= 1
~~~

列表、超链接、Tab、分页符、上下标、图片、修订和嵌套表格使用压力夹具 XML 断言存在且 payload 未被删除。

- [ ] **Step 2: 运行测试确认失败**

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_mapping.py
~~~

预期：因 patch_document_xml 尚不存在失败。

- [ ] **Step 3: 实现精准段落定位和 pStyle 修改**

按照 ElementAnalysis.xml_path 定位段落节点；对 mapped 记录设置 DC_* ID；对 uncertain、preserved、unknown 不改段落样式。没有 w:pPr 时只创建必要节点。表格单元格的 body-table 也只修改其普通段落 w:pStyle，不触碰表格属性。

- [ ] **Step 4: 写并运行 Direct Formatting 失败测试**

先增加测试，验证下列行为：

~~~python
def test_uniform_direct_formatting_is_removed_but_local_semantics_survive():
    output = normalize_fixture_with_uniform_runs()
    assert all_direct_font_properties_absent(output, "uniform paragraph")
    assert direct_bold_present(output, "partial emphasis")
    assert vert_align_present(output, "H₂O")
    assert tab_present(output, "CASE-SPACE-001")
    assert page_break_present(output, "CASE-PAGEBREAK-001")
    assert hyperlink_present(output, "CASE-LINK-001")
~~~

预期新增测试先失败。

- [ ] **Step 5: 实现全段一致性清理并使测试通过**

在 formatting.py 中只处理 rFonts、sz/szCs、color、b/bCs、i/iCs。对于包含文本的所有运行节点，只有某属性在每个运行中显式存在且规范化值一致时才删除该属性；部分运行不一致则保留。永远不删除 vertAlign、underline、strike、highlight、Tab、Break、Field、Drawing、Hyperlink 等节点。

运行：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_mapping.py
~~~

- [ ] **Step 6: 提交映射和格式清理**

~~~powershell
git add src/doc_converter/docx_direct/style_mapper.py src/doc_converter/docx_direct/formatting.py src/doc_converter/docx_direct/ooxml_patch.py src/doc_converter/docx_direct/__init__.py tests/test_docx_direct_mapping.py
git commit -m "feat: map direct docx paragraphs without losing run semantics"
~~~

### Task 6: 编排 Normalizer、审计报告和压力测试验收

**Files:**
- Create: src/doc_converter/docx_direct/audit.py
- Create: src/doc_converter/docx_direct/normalizer.py
- Modify: src/doc_converter/docx_direct/__init__.py
- Test: tests/test_docx_direct_normalizer.py
- Test: tests/test_docx_direct_pressure.py

**Interfaces:**
- Consumes: Task 2–5 的 Analyzer、Classifier、Style Injector、XML Patch，以及现有 StylePack。
- Produces: normalize_docx_direct(source_path, style_pack, output_path, audit_dir=None) -> DirectNormalizeResult，并写出 docx-analysis.json、docx-normalization-report.json、style-pack.snapshot.json。

- [ ] **Step 1: 写 Normalizer/Audit 失败测试**

~~~python
def test_normalizer_never_modifies_source_and_writes_audit_artifacts(tmp_path):
    source = fixture_path()
    output = tmp_path / "normalized.docx"
    audit_dir = tmp_path / "audit"
    before = sha256(source)

    result = normalize_docx_direct(source, create_style_pack(name="test", format_id="docx"), output, audit_dir=audit_dir)

    assert output.is_file()
    assert result.analysis_path == audit_dir / "docx-analysis.json"
    assert result.normalization_report_path == audit_dir / "docx-normalization-report.json"
    assert result.style_pack_snapshot_path == audit_dir / "style-pack.snapshot.json"
    assert sha256(source) == before
    report = json.loads(result.normalization_report_path.read_text(encoding="utf-8"))
    assert report["source_sha256"] == before
    assert report["source_unchanged"] is True
    assert all(item["target_style"] for item in report["elements"] if item["action"] == "mapped")
~~~

再测源输出同路径、无效 DOCX、目标写入失败：源文件必须保持原 SHA-256，目标不得留下半成品，审计文件不得在主流程失败时冒充成功。

- [ ] **Step 2: 运行测试确认失败**

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_normalizer.py
~~~

预期：因 Normalizer/Audit 入口不存在失败。

- [ ] **Step 3: 实现编排和原子输出**

Normalizer 顺序固定为：

~~~text
校验 source/output 路径
→ 分析源 DOCX
→ 分类分析结果
→ 复制源 ZIP 到临时工作文件
→ 增量注入 styles.xml
→ patch document.xml
→ 写入临时输出
→ 将三份审计产物写入临时审计目录
→ 校验输出存在和包可读
→ 原子移动 output.docx 和审计目录
~~~

任何步骤失败都删除临时输出和临时审计目录，既有目标和审计文件不被覆盖。只有 DOCX 校验成功后才原子移动 output.docx 和三份审计产物。Audit 将完整分析结果转 JSON，并记录 source/output SHA-256、元素动作计数、目标 XML 部件、保留原因和 Style Pack 快照。

- [ ] **Step 4: 运行 Normalizer 单元测试并修正到通过**

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_normalizer.py
~~~

预期所有源保护、产物、错误回滚测试通过。

- [ ] **Step 5: 写压力测试结构不变量**

tests/test_docx_direct_pressure.py 使用固定夹具和 normalize_docx_direct()，验证：

~~~python
def test_pressure_document_maps_targets_and_preserves_package_structures(tmp_path):
    result = normalize_docx_direct(fixture_path(), style_pack(), tmp_path / "out.docx", audit_dir=tmp_path / "audit")
    output = result.output_path

    assert paragraph_style_for_text(output, "CASE-H-001 标题层级与正文结构") == "DC_Heading1"
    assert paragraph_style_for_text(output, "一、一级中文编号但使用普通正文样式 〔CASE-MANUAL-001〕") == "DC_Heading1"
    assert paragraph_style_for_text(output, "CASE-TBL-001 表格结构") == "DC_Heading1"
    assert anchors_in_order(output, ["CASE-RUN-ANCHOR", "CASE-SPACE-001", "CASE-LINK-001", "CASE-EN-001", "CASE-REV-001"])
    assert package_payload(output, "word/numbering.xml") == package_payload(fixture_path(), "word/numbering.xml")
    assert package_payload(output, "word/footnotes.xml") == package_payload(fixture_path(), "word/footnotes.xml")
    assert package_payload(output, "word/endnotes.xml") == package_payload(fixture_path(), "word/endnotes.xml")
    assert relationship_targets(output) == relationship_targets(fixture_path())
    assert image_count(output) == image_count(fixture_path()) == 3
    assert table_merge_signature(output) == table_merge_signature(fixture_path())
~~~

结构比较以 XML 语义和 payload 为准，不要求 ZIP 压缩时间戳或 XML 空白字节完全相同；未被替换的 ZIP 部件 payload 应完全相同。

- [ ] **Step 6: 运行压力测试并人工核对审计摘要**

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_docx_direct_normalizer.py tests/test_docx_direct_pressure.py
~~~

然后输出分析结果中的角色计数、mapped/uncertain/preserved 计数和结构比较摘要，确认所有 mapped 项有目标样式、所有压力锚点存在。若用户提供文件与仓库夹具 SHA-256 不一致，立即停止并修正夹具，不继续解释测试结果。

- [ ] **Step 7: 运行全套质量门禁**

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
git diff --check
~~~

预期：新测试和原有 100 个基线测试全部通过；既有弃用警告可以保留但必须在最终报告中说明。

- [ ] **Step 8: 提交核心 Direct Normalizer**

~~~powershell
git add src/doc_converter/docx_direct tests/test_docx_direct_normalizer.py tests/test_docx_direct_pressure.py
git commit -m "feat: add docx direct normalizer pipeline"
~~~

### Task 7: 分支级复核与交付记录

**Files:**
- Test: 已有全部 Python 测试与 Task 6 压力测试

**Interfaces:**
- Consumes: Task 1–6 的提交、设计文档和审计样例。
- Produces: 分支级测试证据、复核记录和明确的未完成边界；不接入 API/UI，不合并 main。

- [ ] **Step 1: 检查变更范围和分支边界**

运行：

~~~powershell
git diff --name-status main...HEAD
git status --short --branch
git log --oneline --decorate main..HEAD
~~~

确认不存在 api.py、importers/docx.py、docx_extensions.py 的非必要修改，不包含 .codegraph/，且 main 无新提交。

- [ ] **Step 2: 复核 Round-trip 回归**

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_importers.py tests/test_renderer.py tests/test_api.py
~~~

预期现有路线测试继续通过，Direct 模块没有改变 Round-trip 输出。

- [ ] **Step 3: 运行最终全套验证并保存结果**

重复 Task 6 的全套质量门禁，读取每一条命令的实际输出，再检查审计报告中 source/output hash、结构计数和动作计数。不得仅依据代码 diff 宣称完成。

- [ ] **Step 4: 进行分支级代码复核**

使用 superpowers:verification-before-completion 和 superpowers:requesting-code-review 的要求复核：源文件保护、XML 只改允许节点、审计完整性、压力测试不变量、Round-trip 不回归。Critical/Important 问题必须补失败测试后修复并重新跑全套；Minor 记录为延后事项。

- [ ] **Step 5: 提交复核结果，不合并 main**

最终只保留实验分支和提交历史，向用户报告：分支名、最新提交、测试结果、压力测试结构保真结果、未实现的 API/UI/DOC 边界，以及任何明确的延后事项。
