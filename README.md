# Doc Converter

完全本地运行、无 AI 参与的文档内容规范化转换应用。支持 Markdown、DOCX 和 DOC 输入。DOCX 默认在原生 OOXML 中直接规范化；Markdown 和 DOC 由后端自动识别元数据和标题层级后生成 DOCX。选择文件后一次点击“开始转换”，即可预览和下载。原始上传文件永不覆盖，文档不上传。

## 当前能力

- 双栏转换器：左侧选择文件，右侧预览结果。MD、DOC、DOCX 共用一次点击转换流程；无内部文档编辑器、准备步骤或结构确认。
- 支持 `.md`、`.markdown`、`.docx` 和 `.doc` 输入。DOCX 默认在原生 OOXML 中依据 hybrid 选定角色映射段落样式，保留表格合并、图片、关系与其他未修改结构；不经过 Markdown，也不调用 Pandoc 导入。DOC 先由 LibreOffice 转成中间 DOCX，再由 Pandoc 导入内部 Markdown。
- 用户下载菜单提供 DOCX 和可选处理报告。原始上传、首次导入 Markdown、规范化 Markdown 和样式快照仍在内部任务目录保留，用于重跑和诊断。切换样式、重复转换始终从首次导入内容开始。
- 样式设置默认折叠为右下角悬浮按钮，需要时展开为固定底部面板，并按“样式角色 / 页面设置”分标签管理；“开始转换”和“下载”作为并列悬浮操作，不必打开设置面板；样式组合支持保存不可变新版本。
- 内置预览按 A4 纸张显示分页页面，使用已生成的 DOCX 转 PDF 结果，不需要滚动到页面底部才能打开设置。
- Markdown 使用独立特征评分和全文编号消歧。充分上下文支持的中等强度候选自动应用；明确的 Front Matter 和正确的标题标记优先。每项记录源行号、候选得分、分差、依据和最终角色，分数不表示统计概率。
- Pandoc 随 Windows 发布包分发；Docker Compose 使用本地 LibreOffice 生成 PDF 预览，Word/WPS 仍可作为用户显式进行高保真复核的最终打开工具。

## Round-trip 保留原则

Markdown 和 DOC 的重建路径以 Pandoc Markdown 的原生能力为第一选择：标题、段落、上下角标、超链接、项目符号、简单表格等直接使用 Pandoc 能读写的 Markdown 表达。只有 Pandoc Markdown 没有对应表达的分页、复杂合并/嵌套表格和 Word 尾注，才使用带明确标记的内部扩展，并在 DOCX 输出阶段恢复为 OOXML 结构。Word 修订内容导入时接受最终版本，避免把修订标记泄漏到内部 Markdown。DOCX 默认使用独立直处理路径，不经过本节的重建步骤。

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

元数据顺序固定为：标题 → 副标题 → 单位 → 部门 → 作者 → 日期 → 摘要 → 关键词。Front Matter 没有填写副标题时，规范化器会识别标题后的短文本行；也会识别正文中的 `摘要：`、`摘要:`、`关键词：` 和 `关键词:`。标题区附近的 `作者：`、`作者单位：`、`单位：`、`部门：` 等显式标签优先；没有标签时，会对标题后的短姓名行（内置常见百家姓）以及包含“公司、中心、部、处、科、室”等机构/部门关键词的短行结合文前位置和相邻信息评分识别。`organization` 和 `department` 是两个独立字段，但在 DOCX 中共用“单位/部门”视觉样式；多个作者按数组顺序用“、”合并。识别出的摘要、关键词、作者和单位不会重复进入正文。

格式调整全部由后端完成。中文公文中的“一、”“（一）”“1.”“（1）”分别根据全文家族和父级判断；小数编号采用显式锚点与编号深度的相对偏移，避免“1.1.1”被压成“1.1”的层级。代码、引用、表格、脚注和真实列表保留其结构；摘要、题名中的链接、强调和脚注也参与实际 DOCX 渲染。

评分规则、质量样本、接口迁移与已知边界见 [自动规范化说明](docs/markdown-auto-normalization.md)。

## DOCX 样式库

每个样式组合都包含以下角色：

当前 DOCX 样式包 schema 为 `docx-style/v3`；读取旧版样式包时会自动迁移，保存时创建新的不可变版本。

`document-title`、`document-subtitle`、`organization-department`、`author`、`date`、`abstract-label`、`abstract-content`、`keywords-label`、`keywords-content`、`heading-1` 至 `heading-6`、`body-paragraph`、`body-table`、`point`、`table-caption`、`figure-caption`、`reference-heading`、`reference-entry`、`footer`、`page`。

摘要和关键词各自只有两套可编辑角色：`abstract-label` / `keywords-label` 是段落角色，设置标签字形并控制标签与内容所在整行的对齐、缩进、行距和段距；`abstract-content` / `keywords-content` 是字符角色，只控制内容文字。旧版样式包的段落设置会迁移到对应的标签角色，标签和内容字体分别保留，不会生成重复角色。生成的表格默认具有 0.5 磅黑色单线外框及内部网格。Markdown 中的 `表1……`、`表一……` 等表题在表格前会映射为 `table-caption`；简单 HTML `<table>` 也会在转换前确定性转成可编辑 Markdown 表格。

样式编辑器的样式角色再按“文前部分 / 正文部分 / 文后部分”分标签。文后部分以单独成行的“参考文献”“参考资料”或 `References`（可带中文/数字章节编号、括号编号、冒号或英文括注）为边界：检测到该标题后，标题使用 `reference-heading`，后续条目使用 `reference-entry`；进入下一章节后恢复正文角色。没有参考文献标题的文档不自动产生文后正文样式。

文字角色可以分别设置中文字体、西文字体、字号、粗体、斜体、颜色；段落角色还可以设置对齐、缩进、行距、段前段后和分页控制。默认值按正式中文文档模板设置：页面为 A4（21.0 cm × 29.7 cm），上下边距 3.5 cm、左右边距 2.8 cm，标题宋体二号，标题区楷体三号，一级标题黑体三号，段落正文仿宋三号且首行缩进 32 pt、固定行距 29 pt，表格正文仿宋四号无缩进，要点楷体三号加粗，页脚宋体四号。

网页编辑器中的字号优先使用“初号、小初、一号、二号、三号、四号、小四”等中文字号，并在括号中显示对应磅值。首行、左右缩进默认按“字符”显示，也可切换为“磅”或“厘米”；切换字号时，字符缩进会保持字符数不变。行距可选择最大值、最小值、固定值或多倍，并按所选类型显示磅值或倍数。

其中“最大值”是 Word OOXML 没有原生约束的兼容选项，导出时使用自动行距规则保留数值；“最小值”“固定值”和“多倍”分别写入 Word 的最小值、固定值和多倍规则。

生成的 DOCX 自包含 `DC_` 前缀样式：

`DC_DocumentTitle`、`DC_DocumentSubtitle`、`DC_OrganizationDepartment`、`DC_Author`、`DC_Date`、`DC_AbstractLabel`、`DC_AbstractContent`、`DC_KeywordsLabel`、`DC_KeywordsContent`、`DC_Heading1` 至 `DC_Heading6`、`DC_BodyParagraph`、`DC_TableBody`、`DC_Point`、`DC_TableCaption`、`DC_FigureCaption`、`DC_ReferenceHeading`、`DC_ReferenceEntry`、`DC_Footer`。

输出不依赖电脑上已有的同名 Word 样式；每个字体同时写入中文和西文四个字体槽位，避免字体回退。文档标题独立使用 `DC_DocumentTitle`，正文 Markdown 的 H1-H6 分别映射到 `DC_Heading1` 至 `DC_Heading6`，不会把二、三级标题压成一级标题。Markdown 粗体映射为“要点”字符样式。项目符号和实际有序列表保留为 Word 列表；明确为普通文字的转义编号行保持普通文字，识别为标题的编号行保留原编号文本。

导出的 DOCX 文件名使用文档标题并清理 Windows 非法字符；没有标题时使用源文件名。

## 架构

| 输入 | 处理链路 | 生成依据 |
| --- | --- | --- |
| MD / Markdown | 首次导入 → 结构解析与评分 → 全文消歧 → 自动规范化 → Pandoc / OOXML 收尾 | 不可变 `source/imported.md` |
| DOC | LibreOffice 转中间 DOCX → Pandoc 导入 → Markdown 自动规范化 | 首次导入与原始上传 |
| DOCX | Analyzer → hybrid 角色决策 → 原生 OOXML 样式映射与输出核验 | 不可变 `source/original.docx` |

三条链路均提供 DOCX 预览与下载。诊断报告不参与用户确认，Markdown 报告写入失败也不阻断 DOCX 生成。

所有网页输入仍输出 DOCX；DOCX 默认走独立的结构保留转换链路。

## 本地运行

开发环境需要 Python 3.12+、[uv](https://docs.astral.sh/uv/)、Node.js；Markdown 和 DOC 重建路径需要 Pandoc。DOC 导入及 PDF 预览需要 LibreOffice；可将 `soffice` 放入 PATH，或通过 `DOC_CONVERTER_LIBREOFFICE` 指定可执行文件。DOCX 直接规范化不要求 Pandoc 或 LibreOffice，缺少 LibreOffice 时仍可下载 DOCX 并使用浏览器内预览回退。

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

脚本默认从 `C:\Program Files\Pandoc\pandoc.exe` 取 Pandoc，也可使用 `-PandocPath` 指定本地文件。Windows 发布包不包含 LibreOffice；导入 `.doc` 时会检测本机安装，缺少 LibreOffice 不影响 Markdown 和 DOCX 输入。

## Docker Compose

Compose 部署包含前端静态资源、FastAPI 服务、Pandoc 和 LibreOffice，项目名固定为 `doc-converter`。任务、样式组合和转换产物保存在命名卷 `doc-converter-data` 中；DOC 输入可直接复用镜像内的 LibreOffice：

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


### 第二轮结构恢复与 Windows Docker 验证

Markdown / DOC 的自动规范化复用原生 DOCX 的编号序列、局部章节模型、真实/虚拟父节点恢复能力，并对实际 DOCX 样式及大纲进行复核。流程仍为一键转换、预览和下载。

- [多阶段架构与复用边界](docs/markdown-auto-normalization-v2-structure-quality.md)
- [新旧质量指标、正确修复覆盖率与性能](docs/markdown-quality-v2-repair-coverage.md)
- [Windows PowerShell 更新、PR worktree 与真实 Docker 验证](docs/windows-docker-v2-startup-verification.md)

Shell 脚本检出固定 LF，镜像构建另做 CRLF 归一；重建容器无需删除数据卷。样式设置显示异常先 Ctrl+F5，首页 HTML 已配置重新验证。

Issue #4 的完整正文 H2/H3 起步修正、保留边界和两条路径输出对照见 [正文根层级归一报告](docs/body-root-normalization-issue-4.md)。
