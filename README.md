# Doc Converter

完全本地运行、无 AI 参与的 Markdown → DOCX 转换应用。

## 设计原则

- 不调用大模型、不上传文档、不改写正文事实。
- 文档语义、视觉样式、DOCX 渲染三层分离。
- 标题、单位、部门、作者、日期等元数据使用标准化 Markdown 协议保存。
- 样式包为本机全局库，可创建、保存新版本并在转换时选择。
- 生成产物可审计：保留标准化 Markdown、用户确认记录、样式快照和转换报告。

## 首版能力

| 能力 | 状态 |
| --- | --- |
| Markdown 结构建议与人工确认 | 已实现首轮标题建议与确认流程 |
| Markdown → 可编辑 DOCX | 已实现 |
| 全局 DOCX 样式库 | 已实现标题、一级标题、正文的可编辑版本化样式包 |
| 内置 DOCX 页面预览 | 已实现（浏览器内渲染生成的 DOCX） |
| Word 原生 PDF 高保真复核 | 规划中 |
| PPTX、XLSX、批量转换、DOCX 样式反向提取 | 未纳入首版 |

## 架构

```text
原始 Markdown
  → 确定性规范化与人工确认
  → normalized-md/v1
  → DOCX 样式包
  → Pandoc
  → 可编辑 DOCX
  → 内置浏览器预览 / 可选 Word PDF 复核
```

Pandoc 将随应用分发。内置预览不依赖 LibreOffice；若启用高保真 PDF 复核，则优先调用本机 Microsoft Word。LibreOffice 只作为用户显式启用的备用引擎。

## 元数据与语义

```yaml
---
schema: normalized-md/v1
title: 项目建设方案
organization: XX公司
department: XX部门
authors:
  - 张三
date: 2026-09-17
---
```

`#` 永远表示正文一级标题，不表示文档标题。低置信度的标题、单位、部门和作者识别只给出建议，必须由用户确认后才会写入标准化结果。

## 本地运行

开发环境需要 Python 3.12+、[uv](https://docs.astral.sh/uv/)、Node.js 和 Pandoc：

```powershell
uv sync --group dev
npm --prefix frontend install
npm --prefix frontend run build
.\run-doc-converter.cmd
```

网页只监听 `127.0.0.1:8765`，启动后会自动在默认浏览器打开。任务与全局样式包默认保存在 `%LOCALAPPDATA%\DocConverter`。

## Windows 发布包

执行下列命令会生成 `release\DocConverter\DocConverter.exe`。发布包内置 Pandoc 与 DOCX 浏览器预览资源；使用者无需安装 LibreOffice。Word 仅在未来启用“高保真 PDF 复核”时才是可选依赖。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

发布脚本默认从 `C:\Program Files\Pandoc\pandoc.exe` 取 Pandoc；也可以用 `-PandocPath` 显式指定。

## 许可证

当前仓库为私有项目，暂不授予第三方使用、复制或分发权利；如需开源发布，将在此处替换为明确的开源许可证。
