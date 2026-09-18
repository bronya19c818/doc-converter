# DOCX 样式编辑器与双栏工作区实施计划

## 目标

让 Markdown → DOCX 支持模板级样式编辑、自包含 Word 样式、稳定字体映射、可编辑 Markdown 工作副本和 A 方案双栏工作区。

## 执行顺序

1. 新增结构化样式模型和旧样式迁移，补齐固定角色与默认模板值。
2. 扩展规范化中间层，解析 Front Matter 元数据，加入工作副本与可应用结构建议。
3. 生成 `DC_` 前缀自包含样式，使用 Pandoc 转换后执行确定性 OOXML 收尾，包括标题区、表格正文、要点、列表和奇偶页页脚。
4. 调整任务 API、动态文件名、草稿保存、来源哈希和产物契约。
5. 将前端改为 42% / 58% 双栏，左侧可编辑 Markdown，右侧内置预览，底部折叠设置面板提供完整样式编辑和下载。
6. 更新 README、Windows 发布脚本并运行 Python/TypeScript 测试、构建、静态检查和浏览器验收。

## 验收重点

- 旧版样式 JSON 可读取并迁移，新建样式包含全部固定角色，修改只创建新版本。
- 标题、副标题、单位、部门、作者、日期顺序稳定；单位和部门共用视觉样式。
- 所有标题（文档标题除外）为 `DC_Heading1`；有序列表无 `numPr`；粗体为 `DC_Point`。
- `styles.xml` 包含全部 `DC_` 样式和四个字体槽位，黑体不会回退为 MS 明朝。
- 输出文件名与文档标题一致，任务下载阻止路径穿越。
- 前端没有阻塞式“请确认结构建议”卡片，设置面板可折叠，下载入口只出现在设置面板。

## 验证命令

```powershell
uv run pytest -q
uv run ruff check .
uv run mypy src
npm test --prefix frontend
npm run build --prefix frontend
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```
