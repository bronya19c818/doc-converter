# Doc Converter

完全本地运行、无 AI 参与的 Markdown → DOCX 转换应用。原始 Markdown 永不覆盖，文档不上传；Pandoc 负责内容转换，应用负责确定性规范化、样式模板和 OOXML 收尾。

## 当前能力

- A 方案双栏工作区：左侧可编辑 Markdown 工作副本，右侧内置 DOCX 预览。
- 样式面板固定在页面底部，可折叠；样式组合支持保存不可变新版本。
- 结构建议只作提示，可直接应用为文档标题或副标题，不再阻塞生成。
- 任务产物包括 DOCX、规范化 Markdown、审计报告和样式快照。
- Pandoc 随 Windows 发布包分发；LibreOffice 不参与自动转换，Word 仅作为用户显式进行高保真复核时的可选工具。

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
---
```

元数据顺序固定为：标题 → 副标题 → 单位 → 部门 → 作者 → 日期。`organization` 和 `department` 是两个独立字段，但在 DOCX 中共用“单位/部门”视觉样式；多个作者按数组顺序用“、”合并。

## DOCX 样式库

每个样式组合都包含以下角色：

`document-title`、`document-subtitle`、`organization-department`、`author`、`date`、`heading-1`、`body-paragraph`、`body-table`、`point`、`table-caption`、`figure-caption`、`footer`、`page`。

文字角色可以分别设置中文字体、西文字体、字号、粗体、斜体、颜色；段落角色还可以设置对齐、缩进、行距、段前段后和分页控制。默认值按正式中文文档模板设置：上下边距 3.5 cm、左右边距 2.8 cm，标题宋体二号，标题区楷体三号，一级标题黑体三号，段落正文仿宋三号且首行缩进 32 pt、固定行距 29 pt，表格正文仿宋四号无缩进，要点楷体三号加粗，页脚宋体四号。

生成的 DOCX 自包含 `DC_` 前缀样式：

`DC_DocumentTitle`、`DC_DocumentSubtitle`、`DC_OrganizationDepartment`、`DC_Author`、`DC_Date`、`DC_Heading1`、`DC_BodyParagraph`、`DC_TableBody`、`DC_Point`、`DC_TableCaption`、`DC_FigureCaption`、`DC_Footer`。

输出不依赖电脑上已有的同名 Word 样式；每个字体同时写入中文和西文四个字体槽位，避免字体回退。文档标题以外的所有 Markdown 标题（H1-H6）都统一映射为一级标题样式。Markdown 粗体映射为“要点”字符样式。列表编号保留为普通文字，不生成 Word 自动编号和自动缩进。

导出的 DOCX 文件名使用文档标题并清理 Windows 非法字符；没有标题时使用源文件名。

## 架构

```text
原始 Markdown
  → 可编辑工作副本
  → 确定性规范化与完整性校验
  → normalized-md/v1 + 样式快照
  → Pandoc + 自包含参考 DOCX
  → OOXML 收尾（DC_ 样式、标题区、表格正文、页脚）
  → 内置浏览器预览与本地产物下载
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
