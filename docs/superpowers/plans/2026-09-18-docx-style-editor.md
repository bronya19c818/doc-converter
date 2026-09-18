# DOCX 样式编辑器与 A4 工作区 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在无 AI、本机处理的架构下，识别副标题/摘要/关键词，增加自包含 DOCX 样式，并把设置与预览改造成可达的悬浮标签式 A4 工作区。

**Architecture:** 规范化器负责从 Front Matter 和文档开头确定性提取标题区元数据；样式 schema 和 OOXML 编译器为每个语义角色生成 `DC_` 前缀样式并设置 A4 section。React 工作区把设置变成固定底部浮层，`docx-preview` 使用 wrapper 和文档页尺寸渲染独立纸张。

**Tech Stack:** FastAPI、Pydantic、python-docx、OOXML、Pandoc、React、TypeScript、Vite、docx-preview、Vitest、pytest。

**Spec:** `docs/superpowers/specs/2026-09-18-docx-style-editor-design.md`

## Global Constraints

- 不调用 AI，不上传文档，原始 Markdown 永不覆盖。
- Front Matter 顺序为标题、 副标题、单位、部门、作者、日期、摘要、关键词。
- 单位和部门保留两个字段，但共用 `DC_OrganizationDepartment`。
- 所有非文档标题均映射为 `DC_Heading1`；有序列表编号作为普通文本，不生成 Word 自动编号。
- DOCX 默认 A4（21.0 cm × 29.7 cm），输出样式全部使用 `DC_` 自定义 ID。
- 设置面板默认折叠，下载入口只出现在“下载产物”标签。
- 测试文本由项目生成，覆盖元数据、标题、列表、表格、图片、链接、代码块和中西文混排。

---

### Task 1: 结构化元数据与样式 schema

**Files:**
- Modify: `src/doc_converter/normalizer.py`
- Modify: `src/doc_converter/style_schema.py`
- Modify: `src/doc_converter/style_library.py`
- Modify: `src/doc_converter/docx_styles.py`
- Test: `tests/test_normalizer.py`
- Test: `tests/test_style_library.py`

**Interfaces:**
- `normalize_markdown(source, filename, confirmed_roles) -> NormalizedDocument` 增加 `abstract` 字符串和 `keywords` 字符串数组的识别与 Front Matter 序列化。
- `ROLE_KEYS`、`default_roles()`、`migrate_roles()` 增加 `abstract`、`keywords`，`PageSpec` 增加 `page_width_cm=21.0`、`page_height_cm=29.7`。
- `ROLE_TO_STYLE_ID` 增加 `abstract: DC_Abstract`、`keywords: DC_Keywords`。

- [ ] **Step 1: Write failing normalizer tests using a generated comprehensive Markdown fixture**

在 `tests/test_normalizer.py` 增加：

```python
def test_leading_subtitle_abstract_and_keywords_are_extracted() -> None:
    source = '''---
title: “人工智能+”行动下全国公共资源交易数智化发展实践与方向研究
---

基于14个省级“AI+公共资源交易”创新样本

摘要：在安全、制度和生态四个方面推进智慧交易。

关键词：人工智能；大模型；公共资源交易；数智化

# 一、引言

正文含有 **重点**、[链接](https://example.com) 和 ![图](images/a.png)。

| 项目 | 数量 |
| --- | ---: |
| A | 10 |
'''
    result = normalize_markdown(source, filename='研究.md', confirmed_roles={})
    assert result.metadata['subtitle'] == '基于14个省级“AI+公共资源交易”创新样本'
    assert result.metadata['abstract'] == '在安全、制度和生态四个方面推进智慧交易。'
    assert result.metadata['keywords'] == ['人工智能', '大模型', '公共资源交易', '数智化']
    assert '摘要：' not in result.markdown
    assert '关键词：' not in result.markdown
    assert '# 一、引言' in result.markdown
    assert result.report['integrity']['passed'] is True
```

同时覆盖 Front Matter 已有字段优先和普通无标点正文不被移动的两个反例。

- [ ] **Step 2: Run the focused normalizer tests and verify they fail**

Run: `uv run pytest tests/test_normalizer.py -q`

Expected: FAIL because `subtitle`/`abstract`/`keywords` are not extracted and the schema order has no new fields。

- [ ] **Step 3: Implement deterministic leading-block extraction**

在 `normalizer.py` 中新增 `_extract_leading_metadata(lines, metadata, first_content_line)`：只扫描首个标题、表格、围栏代码之前的非空块；识别 `摘要`/`关键词` 标签；当标题存在且副标题缺失时，接受单行、≤80 字符、无句末标点的短行作为副标题。解析关键词时按 `；;，,` 与换行拆分。将识别块从正文行移除并把 `line/from/to` 追加到 `report['changes']`。Front Matter 显式字段不覆盖。

把 `_METADATA_KEYS` 更新为 `('title', 'subtitle', 'organization', 'department', 'authors', 'date', 'abstract', 'keywords')`，规范化日期、作者、关键词类型，并保持 `schema: normalized-md/v1` 兼容。

- [ ] **Step 4: Extend style schema and OOXML map**

在 `style_schema.py` 的 `ROLE_KEYS`、`default_roles()` 和迁移逻辑中加入两个段落角色；摘要沿用正文的中文正式文档默认值，关键词沿用正文但首行缩进为 0。给 `PageSpec` 增加 A4 宽高字段，旧 JSON 缺失时补 21.0/29.7。更新 `docx_styles.py` 的 `ROLE_TO_STYLE_ID`。

- [ ] **Step 5: Run focused tests and commit**

Run: `uv run pytest tests/test_normalizer.py tests/test_style_library.py -q`

Expected: PASS；提交：`git add src/doc_converter/normalizer.py src/doc_converter/style_schema.py src/doc_converter/docx_styles.py tests/test_normalizer.py tests/test_style_library.py && git commit -m "feat: extract title metadata and add abstract styles"`。

### Task 2: A4 DOCX 输出与标题区样式

**Files:**
- Modify: `src/doc_converter/docx_postprocess.py`
- Modify: `src/doc_converter/docx_styles.py`
- Modify: `src/doc_converter/renderer.py`
- Test: `tests/test_renderer.py`

**Interfaces:**
- `compile_styles()` 写入 section 的 A4 宽高和页边距。
- `apply_postprocess()` 输出 `DC_Abstract`、`DC_Keywords` 标题区段落。

- [ ] **Step 1: Write failing renderer tests**

在现有 renderer fixture 中加入 subtitle/abstract/keywords，并断言：

```python
assert {'DC_Abstract', 'DC_Keywords'} <= style_ids
assert '摘要：在安全、制度和生态四个方面推进智慧交易。' in text
assert '关键词：人工智能；大模型；公共资源交易；数智化' in text
assert document.sections[0].page_width == Mm(210)
assert document.sections[0].page_height == Mm(297)
```

同时读取 `word/styles.xml`，断言两个 `DC_` styleId 存在，并确保摘要/关键词不重复出现在正文段落中。

- [ ] **Step 2: Run the focused renderer tests and verify they fail**

Run: `uv run pytest tests/test_renderer.py -q`

Expected: FAIL because the new role IDs, metadata entries and A4 section size are absent。

- [ ] **Step 3: Implement A4 section and metadata insertion**

在 `compile_styles()` 中读取 `page_width_cm`/`page_height_cm`，使用 `Cm()` 设置 `section.page_width`/`section.page_height`。在 `_insert_metadata()` 的日期之后插入摘要和关键词；摘要用字符串，关键词用“；”连接，并补上固定标签。`split_metadata()` 和 renderer 继续只将 Front Matter 以外的正文交给 Pandoc。

- [ ] **Step 4: Preserve existing deterministic OOXML behavior**

保持标题 H1-H6 映射、表格正文、粗体 `DC_Point`、删除 `numPr`、奇偶页脚和自包含字体槽位逻辑不变；新增样式必须经过 `migrate_roles()`，不能引用 Normal/Title/Subtitle。

- [ ] **Step 5: Run focused renderer tests and commit**

Run: `uv run pytest tests/test_renderer.py -q`

Expected: PASS；提交：`git add src/doc_converter/docx_postprocess.py src/doc_converter/docx_styles.py src/doc_converter/renderer.py tests/test_renderer.py && git commit -m "feat: render abstract keywords and A4 pages"`。

### Task 3: 前端样式角色与设置标签

**Files:**
- Modify: `frontend/src/StyleEditor.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/api.ts` only if new role/page fields need explicit types
- Test: `frontend/src/StyleEditor.test.tsx`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- `StyleEditor` 增加 `section?: 'roles' | 'page'`，默认 `roles`；`roles` 区显示新增摘要/关键词角色，`page` 区只显示页面设置并保存同一版本。
- App 增加 `settingsTab: 'styles' | 'page' | 'artifacts'`，设置面板折叠时渲染固定悬浮按钮，展开时渲染 `role="tablist"`。

- [ ] **Step 1: Write failing frontend tests**

在 `StyleEditor.test.tsx` 中断言“摘要中文字体”“关键词字号”存在，并在 page section 中只显示页面设置。扩展 `App.test.tsx`：

```tsx
expect(screen.getByRole('button', { name: '打开设置' })).toBeInTheDocument()
fireEvent.click(screen.getByRole('button', { name: '打开设置' }))
expect(screen.getByRole('tab', { name: '样式角色' })).toHaveAttribute('aria-selected', 'true')
fireEvent.click(screen.getByRole('tab', { name: '下载产物' }))
expect(screen.getByRole('heading', { name: '下载产物' })).toBeInTheDocument()
expect(screen.getByRole('button', { name: '收起设置' })).toBeInTheDocument()
```

- [ ] **Step 2: Run focused frontend tests and verify they fail**

Run: `npm test -- --run frontend/src/StyleEditor.test.tsx frontend/src/App.test.tsx`（在 `frontend` 目录执行）。

Expected: FAIL because the roles, floating button and tabs do not exist。

- [ ] **Step 3: Add abstract/keywords to the editor defaults**

在 `ROLE_LABELS`、标题区 `GROUPS` 和 `defaultRoleMap()` 中加入 `abstract`、`keywords`；关键词默认首行缩进 0。保留中文字号选项“中文描述在前、磅值在后”、缩进单位“字符/磅/厘米”和行距类型“最大值/最小值/固定值/多倍”。

- [ ] **Step 4: Split the settings panel into fixed tabs**

将原设置区改为：默认 `settingsOpen=false`；折叠状态只显示固定右下角 `打开设置` 按钮；展开状态是 fixed bottom panel，标题栏有生成和收起，内容区有三个 tab。样式角色标签放样式包选择、新建样式包和 `StyleEditor section="roles"`；页面设置标签使用 `StyleEditor section="page"`；下载产物标签显示所有 artifact 链接。

- [ ] **Step 5: Add accessible responsive styles**

用 `.settings-panel` 的 fixed bottom、最大高度和内部滚动，`.settings-fab` 固定右下角；移动端面板占满宽度，工作区保持纵向排列。为 tab 的选中/焦点态、浮层阴影、按钮触控高度和遮挡关系增加 CSS，不把设置重新放回普通文档流。

- [ ] **Step 6: Run focused frontend tests and commit**

Run: `npm test -- --run` and `npm run build`（在 `frontend` 目录执行）。

Expected: PASS；提交：`git add frontend/src/App.tsx frontend/src/StyleEditor.tsx frontend/src/styles.css frontend/src/api.ts frontend/src/App.test.tsx frontend/src/StyleEditor.test.tsx && git commit -m "feat: add floating tabbed style settings"`。

### Task 4: A4 内置预览

**Files:**
- Modify: `frontend/src/DocxPreview.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/DocxPreview.test.tsx` (create)

**Interfaces:**
- `DocxPreview` 保持 `documentUrl` 属性；调用 `renderAsync` 时传递 wrapper、分页、页眉页脚和 lastRenderedPageBreak 选项。

- [ ] **Step 1: Write a failing preview test with a mocked dynamic import**

新增测试以 mock `fetch` 和 `docx-preview`，调用 `renderAsync` 后断言选项包含：

```ts
expect(options).toMatchObject({
  breakPages: true,
  inWrapper: true,
  renderHeaders: true,
  renderFooters: true,
  ignoreLastRenderedPageBreak: false,
})
```

- [ ] **Step 2: Run the focused preview test and verify it fails**

Run: `npm test -- --run src/DocxPreview.test.tsx`（在 `frontend` 目录执行）。

Expected: FAIL because `inWrapper` is currently false and the last-rendered break option is absent。

- [ ] **Step 3: Enable wrapper pagination and style the paper stage**

设置 `inWrapper: true`、`ignoreLastRenderedPageBreak: false`；将预览工作台设为独立滚动区域，wrapper 使用纵向 flex，页面使用 A4 CSS 变量、白色背景、阴影和页面间距。不要设置 `overflow: hidden` 以免裁掉正文。

- [ ] **Step 4: Run preview tests and commit**

Run: `npm test -- --run src/DocxPreview.test.tsx frontend/src/App.test.tsx` and `npm run build`。

Expected: PASS；提交：`git add frontend/src/DocxPreview.tsx frontend/src/DocxPreview.test.tsx frontend/src/styles.css && git commit -m "feat: render DOCX in A4 paper preview"`。

### Task 5: API、测试夹具、README 与验证

**Files:**
- Modify: `src/doc_converter/api.py`
- Modify: `tests/test_api.py`
- Modify: `README.md`
- Create: `tests/fixtures/comprehensive.md`
- Modify: `scripts/build-windows.ps1` only if the frontend build copy path changes

- [ ] **Step 1: Write API tests for automatic subtitle and metadata suggestions**

用 `tests/fixtures/comprehensive.md` 创建任务，断言保存草稿和 normalize/render 后的 `suggestions` 不再要求确认，生成产物名称仍来自标题，审计报告包含 subtitle/abstract/keywords 变化。

- [ ] **Step 2: Run API tests and fix only contract regressions**

Run: `uv run pytest tests/test_api.py -q`。

Expected: PASS；如果既有测试只断言旧 suggestions，更新断言以反映“识别后无需确认但兼容接口仍存在”。

- [ ] **Step 3: Add the comprehensive generated fixture**

写入 `tests/fixtures/comprehensive.md`，包含无敏感用户文件的标题区、中文/西文混排、三级标题、列表、表格、图片引用、链接、代码块、摘要和关键词，供 normalizer/renderer/API 复用。

- [ ] **Step 4: Update README**

补充 Front Matter 示例、自动副标题/摘要/关键词识别、两个新增样式角色、A4 预览、浮动标签设置、所有 DOCX 使用自包含 `DC_` 样式，以及 Pandoc 打包和 LibreOffice 不参与自动转换的说明。

- [ ] **Step 5: Run the full verification suite**

Run:

```powershell
uv run pytest -q
uv run ruff check .
uv run mypy src
Push-Location frontend
npm test -- --run
npm run build
Pop-Location
```

Expected: all commands pass。最后检查 `git diff --check`、`git status --short`，确认只包含本次改动并提交：`git add docs/superpowers src tests frontend README.md scripts && git commit -m "feat: improve metadata recognition and A4 workspace"`。
