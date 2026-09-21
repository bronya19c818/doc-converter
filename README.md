# Doc Converter

完全本地运行、无 AI 参与的 Markdown → DOCX 转换应用。原始 Markdown 永不覆盖，文档不上传；Pandoc 负责内容转换，应用负责确定性规范化、样式模板和 OOXML 收尾。

## 当前能力

- A 方案双栏工作区：左侧可编辑 Markdown 工作副本，右侧内置 DOCX 预览。
- 样式设置默认折叠为右下角悬浮按钮，需要时展开为固定底部面板，并按“样式角色 / 页面设置”分标签管理；“生成”和“下载”作为并列悬浮操作，不必打开设置面板；样式组合支持保存不可变新版本。
- 内置预览按 A4 纸张显示分页页面，使用已生成的 DOCX 转 PDF 结果，不需要滚动到页面底部才能打开设置。
- 结构建议是可执行的确定性动作：可将标题区内容应用为文档标题、副标题、摘要、关键词、作者、单位、部门或日期；应用会直接写入 Markdown Front Matter 并从标题区移除原行，不再阻塞生成。
- 任务产物包括 DOCX、规范化 Markdown、审计报告和样式快照。
- Pandoc 随 Windows 发布包分发；Docker Compose 使用本地 LibreOffice 生成 PDF 预览，Word/WPS 仍可作为用户显式进行高保真复核的最终打开工具。

## Markdown 二次整理

规范化前会对常见 Markdown/OCR 导出问题执行一遍可审计的本地整理，不调用 AI，也不覆盖原始文件：

- 将被统一写成 `#` 的中文章节、括号编号、数字编号和小数编号重建为对应的标题层级；原本明确写成 `##`、`###` 的非编号标题保留其层级。
- 检测到技术标准编号（例如 `Q/GDW 1234—2024`）时，也会把安全可识别的裸编号行（如 `5.1 盘点范围`）转换为对应层级；带有“应、不得、负责”等正文语气的编号句不会自动升格。
- 删除 `目次` 标题及其到下一标题前的目录行，删除重复出现的独立标准号页眉。
- 只合并有明显跨页断裂特征的段落片段；标题、表格、摘要、关键词、作者、单位、部门和日期等结构行不会被当作断行拼接。

每一项整理都会写入审计报告的 `changes`，便于在发现误判时定位规则；Dify 流水线中会复制上下文或改写内容的分块逻辑不进入本应用。

## Front Matter

```yaml
---
schema: normalized-md/v1
title: 项目建设方案
subtitle: 实施说明
organization: XX公司
department: XX部门
authors:
  - 张三
  - 李四
date: 2026-09-18
abstract: 本文摘要内容。
keywords:
  - 关键词一
  - 关键词二
---
```

元数据顺序固定为：标题 → 副标题 → 单位 → 部门 → 作者 → 日期 → 摘要 → 关键词。Front Matter 没有填写副标题时，规范化器会识别标题后的短文本行；也会识别正文中的 `摘要：`、`摘要:`、`关键词：` 和 `关键词:`。标题区附近的 `作者：`、`作者单位：`、`单位：`、`部门：` 等显式标签优先；没有标签时，会对标题后的短姓名行（内置常见百家姓）以及包含“公司、中心、部、处、科、室”等机构/部门关键词的短行进行保守识别。`organization` 和 `department` 是两个独立字段，但在 DOCX 中共用“单位/部门”视觉样式；多个作者按数组顺序用“、”合并。识别出的摘要、关键词、作者和单位不会重复进入正文。

工作区的“结构建议”会显示原始行号和可执行的“应用为……”按钮。应用动作不是只在本次渲染时记忆确认，而是把对应 role 真正写回工作副本的 Front Matter：`author` 写为 `authors` 数组，`keywords` 写为关键词数组，其余角色写为对应标量字段。建议带有原文锚点，所以连续应用多个动作时不会因前面删除行而错位；保存工作副本后，后端会重新扫描剩余未标注内容。

## DOCX 样式库

每个样式组合都包含以下角色：

当前 DOCX 样式包 schema 为 `docx-style/v3`；读取旧版样式包时会自动迁移，保存时创建新的不可变版本。

`document-title`、`document-subtitle`、`organization-department`、`author`、`date`、`abstract-label`、`abstract-content`、`keywords-label`、`keywords-content`、`heading-1` 至 `heading-6`、`body-paragraph`、`body-table`、`point`、`table-caption`、`figure-caption`、`reference-heading`、`reference-entry`、`footer`、`page`。

摘要和关键词各自只有两套可编辑角色：`abstract-label` / `keywords-label` 是段落角色，设置标签字形并控制标签与内容所在整行的对齐、缩进、行距和段距；`abstract-content` / `keywords-content` 是字符角色，只控制内容文字。旧版样式包的段落设置会迁移到对应的标签角色，标签和内容字体分别保留，不会生成重复角色。生成的表格默认具有 0.5 磅黑色单线外框及内部网格。Markdown 中的 `表1……`、`表一……` 等表题在表格前会映射为 `table-caption`；简单 HTML `<table>` 也会在转换前确定性转成可编辑 Markdown 表格。

样式编辑器的样式角色再按“文前部分 / 正文部分 / 文后部分”分标签。文后部分以单独成行的“参考文献”“参考资料”或 `References`（可带中文/数字章节编号、括号编号、冒号或英文括注）为边界：检测到该标题后，标题使用 `reference-heading`，后续条目使用 `reference-entry`；没有参考文献标题的文档不自动产生文后正文样式。

文字角色可以分别设置中文字体、西文字体、字号、粗体、斜体、颜色；段落角色还可以设置对齐、缩进、行距、段前段后和分页控制。默认值按正式中文文档模板设置：页面为 A4（21.0 cm × 29.7 cm），上下边距 3.5 cm、左右边距 2.8 cm，标题宋体二号，标题区楷体三号，一级标题黑体三号，段落正文仿宋三号且首行缩进 32 pt、固定行距 29 pt，表格正文仿宋四号无缩进，要点楷体三号加粗，页脚宋体四号。

网页编辑器中的字号优先使用“初号、小初、一号、二号、三号、四号、小四”等中文字号，并在括号中显示对应磅值。首行、左右缩进默认按“字符”显示，也可切换为“磅”或“厘米”；切换字号时，字符缩进会保持字符数不变。行距可选择最大值、最小值、固定值或多倍，并按所选类型显示磅值或倍数。

其中“最大值”是 Word OOXML 没有原生约束的兼容选项，导出时使用自动行距规则保留数值；“最小值”“固定值”和“多倍”分别写入 Word 的最小值、固定值和多倍规则。

生成的 DOCX 自包含 `DC_` 前缀样式：

`DC_DocumentTitle`、`DC_DocumentSubtitle`、`DC_OrganizationDepartment`、`DC_Author`、`DC_Date`、`DC_AbstractLabel`、`DC_AbstractContent`、`DC_KeywordsLabel`、`DC_KeywordsContent`、`DC_Heading1` 至 `DC_Heading6`、`DC_BodyParagraph`、`DC_TableBody`、`DC_Point`、`DC_TableCaption`、`DC_FigureCaption`、`DC_ReferenceHeading`、`DC_ReferenceEntry`、`DC_Footer`。

输出不依赖电脑上已有的同名 Word 样式；每个字体同时写入中文和西文四个字体槽位，避免字体回退。文档标题独立使用 `DC_DocumentTitle`，正文 Markdown 的 H1-H6 分别映射到 `DC_Heading1` 至 `DC_Heading6`，不会把二、三级标题压成一级标题。Markdown 粗体映射为“要点”字符样式。列表编号保留为普通文字，不生成 Word 自动编号和自动缩进。

导出的 DOCX 文件名使用文档标题并清理 Windows 非法字符；没有标题时使用源文件名。

## 架构

```text
原始 Markdown
  → 可编辑工作副本
  → 确定性规范化与完整性校验
  → normalized-md/v1 + 样式快照
  → Pandoc + 自包含参考 DOCX
  → OOXML 收尾（DC_ 样式、标题区、表格正文、页脚）
  → A4 分页的内置浏览器预览与本地产物下载
```

## 本地运行

开发环境需要 Python 3.12+、[uv](https://docs.astral.sh/uv/)、Node.js 和 Pandoc：

```powershell
uv sync --group dev
npm --prefix frontend install
npm --prefix frontend run build
.\run-doc-converter.cmd
```

网页只监听 `127.0.0.1:8765`，任务与全局样式包默认保存在 `%LOCALAPPDATA%\DocConverter`。服务只读取本地文件，不提供远程上传能力。

## Windows 发布包

下列命令会生成 `release\DocConverter\DocConverter.exe`，并将 Pandoc 与内置预览资源打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

脚本默认从 `C:\Program Files\Pandoc\pandoc.exe` 取 Pandoc，也可使用 `-PandocPath` 指定本地文件。LibreOffice 不会被脚本安装或自动调用。

## Docker Compose

Compose 部署包含前端静态资源、FastAPI 服务和 Pandoc，项目名固定为 `doc-converter`。任务、样式组合和转换产物保存在命名卷 `doc-converter-data` 中：

```powershell
docker compose -p doc-converter up --build -d
```

启动后访问 <http://127.0.0.1:8765/>；查看状态或停止服务：

```powershell
docker compose -p doc-converter ps
docker compose -p doc-converter logs -f app
docker compose -p doc-converter down
```

默认宿主机端口为 `8765`，可通过 `DOC_CONVERTER_PORT=9876` 修改。容器内使用 Pandoc + OOXML 转换，并用 LibreOffice 将已生成 DOCX 转为 PDF 预览；Windows 默认只读挂载 `C:\Windows\Fonts`，使预览使用与最终打开文档相同的中文字体。字体目录不在默认位置时，可通过 `DOC_CONVERTER_WINDOWS_FONTS` 指定。

## 验证

```powershell
uv run pytest -q
uv run ruff check .
uv run mypy src
npm test --prefix frontend
npm run build --prefix frontend
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

## 许可证

当前仓库为私有项目，暂不授予第三方使用、复制或分发权利；如需开源发布，将在此处替换为明确的开源许可证说明。
