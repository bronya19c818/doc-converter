# DOCX Direct Normalizer 设计说明

## 目标

在 `experiment/docx-direct-normalizer` 分支验证一条独立的 DOCX → DOCX 原位规范化路线：复制原始 DOCX，读取其原生 OOXML 结构和版式证据，只有在高置信识别出既有 Style Pack 角色时才局部修改目标段落样式；无法确定的内容以及未被要求修改的 OOXML 保持原样。

本设计以用户提供的压力测试文件为验收基线：

`C:\Users\Lenovo\Downloads\DOCX转Markdown压力测试_V1_结构兼容性.docx`

该文件当前可正常读取，包含 86 个正文段落、4 个表格、3 个分节、3 个图片，以及 Heading 1–6、普通编号标题、上下标、Tab、超链接、列表、合并/嵌套表格、分页符、脚注、尾注、修订、页眉和页脚等结构。

## 分支与范围

- `main` 保留现有 DOCX → Markdown → DOCX Round-trip 路线，不删除、不覆盖、不大规模重构。
- 当前分支为 `experiment/docx-direct-normalizer`，从当前 `main` 提交 `f21d47e` 创建。
- 本次实现范围为 Phase 0–5：实验分支、只读 Analyzer、Style Injection、Paragraph Style Mapping、保守 Direct Formatting 清理、表格正文样式映射。
- API/UI 接入、DOC 输入链路、页面/分节设置规范化不属于本次实现范围。
- 不引入 OCR、AI 分类、复杂公式解析、项目符号重建、复杂表格重建、超链接/脚注/尾注重建或 DOCX → Markdown 中间格式。

## 现状复用边界

当前 `StylePack`、`style_schema.py` 和 `docx_styles.py` 已定义完整的 DOCX 角色以及 `DC_*` 样式编译逻辑。Direct 路线复用这些定义，不重新设计 Style Pack schema，也不把 Direct 逻辑塞进现有 `api.py`、`importers/docx.py` 或 `docx_extensions.py`。

当前 `importers/docx.py` 继续承担 Round-trip 导入职责。Direct Normalizer 使用独立的 Python 调用入口，不改变现有上传任务的 Markdown draft 语义。

## 模块结构

新增：

```text
src/doc_converter/docx_direct/
├── __init__.py
├── model.py
├── analyzer.py
├── classifier.py
├── style_injector.py
├── style_mapper.py
├── formatting.py
├── ooxml_patch.py
├── audit.py
└── normalizer.py
```

职责边界如下：

- `model.py`：定义可序列化的 `ElementAnalysis`、`DocumentAnalysis`、`NormalizationRecord` 和 `DirectNormalizeResult`。
- `analyzer.py`：只读解析 `word/document.xml`、段落样式、段落/运行属性、编号、表格上下文和文档区域；不写源文件。
- `classifier.py`：从分析结果推断既有 Style Pack 角色、置信度、理由和动作状态。
- `style_injector.py`：从现有 `compile_styles()` 生成 `DC_*` 样式模板，只把原 `styles.xml` 中缺失的目标样式增量插入。
- `style_mapper.py`：依据高置信映射结果修改目标段落的 `w:pStyle`，不重建段落、表格或运行节点。
- `formatting.py`：对已映射段落执行全段一致性 Direct Formatting 清理，只处理明确允许接管的字体/字号/颜色/粗体/斜体属性。
- `ooxml_patch.py`：复制 DOCX ZIP 包、按文档顺序定位段落、写回被允许修改的 XML 部件，并保证源文件不变。
- `audit.py`：写出分析报告、规范化报告和 Style Pack 快照。
- `normalizer.py`：编排分析、分类、注入、映射、清理、审计和原子输出。

## 对外入口

主入口为：

```python
normalize_docx_direct(
    source_path: Path,
    style_pack: StylePack,
    output_path: Path,
    *,
    audit_dir: Path | None = None,
) -> DirectNormalizeResult
```

`audit_dir` 未提供时使用 `output_path.parent`。结果至少包含：

```python
DirectNormalizeResult(
    output_path=Path,
    analysis_path=Path,
    normalization_report_path=Path,
    style_pack_snapshot_path=Path,
    analysis=DocumentAnalysis,
)
```

源路径和目标路径相同、源文件不是有效 DOCX ZIP、目标父目录不可写或 XML 无法安全修改时，入口抛出明确异常，并且不产生不完整的最终 DOCX；源文件永不覆盖。

## Analyzer 设计

Analyzer 以 `word/document.xml` 为主文档源，按 `w:body` 的真实子节点顺序遍历普通段落和表格单元格中的段落。页眉、页脚、关系、图片、编号、脚注、尾注和其他未参与规范化的部件不被重建；页眉页脚只作为包结构保留，不自动套用新样式。

每个可处理段落生成一个稳定的 `p-0001` 形式的 `element_id`，并至少记录：

```text
element_id
element_type
text
document_order
region                  # preface / body / postface
original_style_id
original_style_name
alignment
font_size_pt
bold
italic
paragraph_properties
run_properties
numbering_properties
table_context
has_hyperlink
has_tab
has_manual_break
has_drawing
has_field
role
confidence
reasons
```

段落识别和后续 XML 修改使用同一套文档顺序遍历，因此不依赖文本内容作为唯一定位键；重复文本、空文本段落和表格内重复段落不会互相覆盖。

## 文档区域和角色分类

分类继续使用现有 Style Pack 角色，不新增平行角色体系。支持的首批目标角色为：

```text
document-title
document-subtitle
organization-department
author
date
heading-1 ~ heading-6
body-paragraph
body-table
table-caption
figure-caption
reference-heading
reference-entry
```

动作状态固定为：

```text
mapped       confidence >= 0.90 且存在目标角色
uncertain    0.70 <= confidence < 0.90，写入报告但不修改源段落
preserved    confidence < 0.70、角色未知或属于保留结构
```

分类优先级如下：

1. 原生 `Heading 1`–`Heading 6`、`outlineLvl` 和明确的段落语义优先于文本启发式。
2. 文前第一个非摘要、非关键词、非作者/单位/部门/日期、居中且字号明显最大的合理文本识别为 `document-title`。
3. 标题后紧邻的独立、居中且字号较小的文本识别为 `document-subtitle`；不合并两个原始段落，也不把软换行错误拆成多个段落。
4. 文前显式标签以及日期、机构、作者等确定性文本映射到已有角色。
5. 普通样式但以 `一、`、`（一）`、`1.`、`1、`1.1`、`1.1.1`、`（1）`、`①`、`第 X 章`、`第 X 节`、`〔…〕` 或 `【…】` 开头，且独立成段、长度不超过 35 字、以文字结束的段落，按编号层级识别为标题候选；以正文标点结尾的编号句不自动升格。
6. `参考文献`、`参考资料`、`References` 等独立边界之后进入 `postface`；边界行映射为 `reference-heading`，后续非空条目映射为 `reference-entry`。
7. 文档主体中没有自动编号/项目符号的普通非空段落映射为 `body-paragraph`；带 `w:numPr` 或列表样式的段落默认 `preserved`，避免改变列表语义。
8. 表格单元格中的普通段落映射为 `body-table`，只修改段落样式，不修改表、行、单元格、合并、宽度、边框或嵌套表。
9. `表…`/`表一…` 和 `图…`/`图一…` 等独立题注可映射为 `table-caption` 或 `figure-caption`；图片本身不移动、不重新生成。
10. 自定义样式、复杂对象、空段落、域、修订、列表和无法确定的内容保持原样并记录原因。

## Style Injection

Style Injector 使用现有 `compile_styles()` 在临时 `Document()` 中编译 Style Pack，再提取 `ROLE_TO_STYLE_ID` 对应的 `DC_*` 样式元素。

写回原文档时：

- 只打开并修改 `word/styles.xml`；不替换整个 styles 部件。
- 原 `w:style` 全部保留；不存在的 `DC_*` 样式才插入。
- 已存在的同名 `DC_*` 样式不覆盖，避免重复运行时无谓改变原文件。
- 不把临时文档的 `docDefaults`、页面设置、主题、编号或关系复制到源文档。
- 其他 ZIP 部件只复制原始 payload，不重新生成。

## Paragraph Style Mapping

对 `action == "mapped"` 的段落，只修改对应 `w:pPr/w:pStyle/@w:val` 为 `DC_*` 目标 ID。若段落没有 `w:pPr`，只创建必要的 `w:pPr` 和 `w:pStyle` 节点。

以下内容不由 Mapper 重建或删除：

```text
w:numPr / numbering.xml
w:hyperlink / document.xml.rels
w:tab
w:br，包括 page break
w:drawing / 图片关系
w:fldSimple / instrText / field
w:ins / w:del 修订节点
w:vertAlign 上下标
表格结构、合并属性、嵌套表格、宽度和边框
```

## Direct Formatting 清理

只有成功映射的段落进入 `formatting.py`。对包含文本的运行节点，按属性分别判断是否所有运行都具有同一份直接格式；只有全段一致时才移除该属性，使目标段落样式接管：

```text
rFonts
sz / szCs
color
b / bCs
i / iCs
```

若只有部分运行具有粗体、斜体、颜色或字号，则视为局部语义并全部保留。以下属性第一版永不自动删除：

```text
vertAlign
underline
strike
highlight
hyperlink
tab
manual line break
page break
field
drawing
image
formula
bookmark
```

清理只删除允许的 `w:rPr` 子节点，不清空整个运行格式节点，也不改写文本内容。

## 审计产物

每次成功运行都写出：

- `docx-analysis.json`：完整 `DocumentAnalysis`，包含所有段落的原始证据和分类结果。
- `docx-normalization-report.json`：每个元素的原样式、识别角色、置信度、动作、目标样式和理由，并包含 source/output SHA-256、映射数量、保留数量、未确定数量和修改的 XML 部件。
- `style-pack.snapshot.json`：本次使用的完整 Style Pack 快照。

规范化报告中的 `preserved` 和 `uncertain` 记录必须说明保留原因；`mapped` 记录必须有 `target_style`。报告不得写入密码、临时凭据或源文件之外的隐私信息。

## 压力测试与验收

将用户提供的 DOCX 固化为 `tests/fixtures/DOCX转Markdown压力测试_V1_结构兼容性.docx`，自动化测试使用仓库内副本，人工复核仍以用户提供的原文件为源。测试不得修改 Downloads 中的原文件。

验收分为两类：

### 应规范化

- Heading 1–6 映射到 `DC_Heading1`–`DC_Heading6`。
- 普通样式的中文/数字编号标题被高置信识别并映射。
- 文档标题、副标题和文前元数据按原始段落边界识别。
- 普通正文映射到 `DC_BodyParagraph`。
- 表格普通段落映射到 `DC_TableBody`。
- 目标样式在 `word/styles.xml` 中存在，且原有样式仍存在。
- 每个映射结果都出现在审计报告中。

### 必须保持

至少验证以下锚点和结构在输出中仍存在且顺序一致：

```text
CASE-RUN-ANCHOR / H₂O / x²
CASE-SPACE-001 / Tab
CASE-LINK-001 / Hyperlink
CASE-LIST-B1 / 自动列表与编号属性
CASE-TBL-001 / 合并单元格 / 纵向合并 / 嵌套表
CASE-PAGEBREAK-001 / 分页符
CASE-EN-001 / endnotes.xml
CASE-REV-001 / 修订最终内容
```

此外检查：图片数量和关系、`word/numbering.xml`、`word/footnotes.xml`、`word/endnotes.xml`、页眉页脚、关系文件、分节数量、表格合并属性和嵌套表数量不因 Direct 路线重建而丢失。源文件 SHA-256 和源文件 payload 必须保持不变。

## 错误处理与安全边界

- 先将源 DOCX 复制到临时工作副本，再生成临时输出，全部成功后原子移动到目标路径。
- 任意分析、分类、XML 解析或 ZIP 写入失败时删除临时文件，不覆盖源文件和既有目标文件。
- 不调用 Pandoc、LibreOffice 或现有 Markdown importer。
- 不将 Direct DOCX 伪装成 Markdown draft，也不修改现有 API 行为。
- 测试基线和 Direct 测试失败时分别报告，不能把现有 Round-trip 的失败归因于新路线。

## 非本次范围的后续入口

待 Phase 0–5 通过压力测试后，再单独设计：

1. Direct Job 的 API 和结构识别结果 UI。
2. 页面/分节设置的安全映射。
3. `.doc` → LibreOffice 中间 DOCX → Direct Normalize。
4. 与现有 Round-trip importer 的 A/B 结果报告和替换决策。

在这些验收完成前，不删除 Round-trip 实现，不合并到 `main`。
