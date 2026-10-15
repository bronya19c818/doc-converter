# Markdown Auto Normalization Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline implementation and a fresh whole-branch code review.

**Goal:** 完成 Issue #1 的后端自动规范化和前端一键转换。

**Architecture:** 独立 Markdown 评分模块复用候选审计模型；normalizer 统一执行判定，API 固定原始输入，前端仅负责上传与转换。保持 DOCX-direct 不变。

**Tech Stack:** Python 3.12、MarkdownIt、FastAPI、Pandoc、React、TypeScript、Vitest。

**Spec:** ../specs/2026-10-14-markdown-auto-normalization-design.md

## Global Constraints

- 无云端 AI、OCR、多文件作业或新的校对界面。
- 显式结构与内容完整性优先；以准确率和自动覆盖率为目标。
- 不修改 DOCX 原生评分和执行策略。
- 用户已授权连续实施和创建 PR；不合并 main。

## Review Focus

- 多行段落、空标签后的摘要续段不能丢失或重复。
- 中文公文与小数编号混用、同家族重复起号不能漂移。
- 多层列表、围栏内伪标题、脚注定义不能被升格或重排。
- Front Matter 与正文同名内容不能被误覆盖或重复抽取。
- 失败重试及样式切换始终读取首次导入源，预览和下载不能显示错误任务。

### Task 1: Markdown 评分与规范化

Files: `src/doc_converter/markdown_scoring.py`, `normalizer.py`, `markdown_preprocess.py`, `docx_postprocess.py`; tests: `tests/test_markdown_scoring.py`, `tests/test_normalizer.py`, `tests/test_renderer.py`。

Interface: `analyze_markdown(lines, metadata, line_map, config=None)` 返回块判定与全文锚点；`normalize_markdown(source, filename=...)` 自动执行。

- [x] 写失败测试：元数据全角色、显式层级、全文六类编号、代码/列表/脚注完整性与中置信自动应用。
- [x] 运行 targeted pytest 确认 RED；实现独立评分、全文消歧、结构保护与审计。
- [x] 修改旧“未确认不处理”断言；运行 normalizer/renderer/scoring 回归并提交。

### Task 2: 不可变输入 API

Files: `src/doc_converter/api.py`, `tests/test_api.py`。

Interface: render 仅接收样式 ID/version，从 imported.md 读取；只读 draft 兼容，不再建议或写草稿。

- [x] 写 RED 测试：连续重跑、切换样式、污染 work 文件不影响输出、旧参数报错、DOC 导入自动转换。
- [x] 实现并删除重复建议规则与确认产物；测试通过并提交。

### Task 3: 前端一次点击

Files: `frontend/src/App.tsx`, `api.ts`, `styles.css`, `App.test.tsx`。

Interface: `normalizeAndRender(jobId, stylePack)`；无 Markdown 读取或写回。

- [x] 替换旧编辑流程测试，RED 覆盖 MD/DOC/DOCX 一键完成、失败重试、样式切换、设置/全屏键盘操作。
- [x] 删除编辑与建议职责，保留预览下载；运行 Vitest 和 TypeScript/build；浏览器验收。

### Task 4: 验收与交付

Files: `scripts/verify_markdown_scoring.py`, `tests/fixtures/markdown_scoring/`, `README.md`, `docs/markdown-auto-normalization.md`, `.github/workflows/ci.yml`。

- [x] 增加人工规则标注样本和长文档指标，运行全量 pytest、Ruff、Mypy、Vitest、build 和原生 DOCX 验收。
- [x] 更新接口迁移说明、样例结果及限制；独立代码审查后修复重要发现。
- [x] 基于原始 main 创建提交并更新独立远端分支，创建关联 Issue #1 的 PR。


## 执行记录与审查闭环

- 基线使用 GitHub 接口读取私有仓库，独立分支 feat/issue-1-auto-normalization；本地为 main 文本快照。二进制原件保持远端原 SHA，未替换或提交本地重建样本。
- 自动规范化、不可变输入、前端一键转换分别完成 RED→GREEN 验证；Ruff、Mypy、23 项前端测试和生产构建通过。
- 整体独立审查发现 5 项重要问题：元数据引用定义丢失、代码 HTML 转换、实际列表合段、审计/渲染角色分歧、小数锚点压平。均已写失败用例并修复。附带 3 项边界问题（连续摘要、无标点正文动作、链接内分隔符）同样完成回归。
- 最终相关后端 120 项通过；230 个独立标注项和 61 个标题全部符合该受控样本口径。真实 MD、DOC、DOCX 的应用 API 完成导入/生成/预览/下载，使用本地 Pandoc 与 LibreOffice 实际运行。
- 浏览器验收受环境阻塞：本地缺少 Chromium，官方浏览器包下载被截断；云浏览器无法访问此运行环境的 localhost。未把 Vitest/build 记为真实浏览器视觉通过。独立 CJK 字体同样未安装，不声称本地 PDF 字形已完成视觉验收。
- CI 在 GitHub 使用原仓库二进制夹具执行全量及既有 DOCX 原生验收；最终结果记录在 PR。
- Ruling: 用户明确授权连续实施和创建 PR，跳过阶段批准；不合并 main。
- Ruling: 旧 draft GET 只读兼容，PUT 返回 410，旧 render 编辑/确认字段返回 422；旧客户端需迁移，不能静默忽略编辑内容。
- Ruling: 首次导入丢失时仅从原始上传恢复，不回退可编辑草稿；原件缺失须重新上传。
- 审查未覆盖的并发同任务请求与真实业务统计保持既有范围边界；当前前端锁定同一次转换，不引入多文件/多用户作业。DOCX 原生评分内部未改，使用既有回归核验。
