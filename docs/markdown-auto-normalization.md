# Markdown 自动规范化与一键转换

## 一次点击完成导入、识别与生成

选择 `.md`、`.markdown`、`.doc` 或 `.docx`，点击“开始转换”，完成后预览、下载 DOCX。需要局部修改时，可编辑原始文件后重新转换，或直接编辑输出 DOCX。转换器内不再提供 Markdown 编辑、保存副本、结构建议和确认按钮。

内部中间文件保留用于诊断和重新生成。每次 Markdown/DOC 生成均读取首次导入的 `source/imported.md`，不读取上次规范化结果或旧工作副本；旧任务缺少首次导入时仅从原始上传重新导入，原件缺失则明确提示重新上传。DOCX 保持原生 hybrid 路径。

## Markdown 特征与全文证据共同决定角色

MarkdownIt 解析段落、标题、表格、列表、代码和引用，保留源切片与行号；原有预处理中的标题推断不再运行。候选共享 DOCX 的 RoleCandidate、ScoreEvidence 和阈值配置类型，Markdown 单独使用标记、长度、标签、位置、编号家族、句末标点、正文动作与相邻内容证据，不使用 Word 字号或对齐权重。

显式 Front Matter 优先；正确的明确标题层级保留；扁平编号标题结合全文家族与父级重建。小数编号的显式锚点记录“样式层级－编号深度”，后代按该偏移递进。中文与数字括号编号分别判断，不机械设为同级。

默认中等强度阈值为 65、高强度阈值为 85；阈值用于审计强度区间。短编号标题获得编号 35、长度 15、无句末标点 10、全文结构 15 的独立证据，达到 75 后自动处理。该分数表示规则支持强度，不是概率。

单位和部门分别写入 organization / department，再共用 DC_OrganizationDepartment 样式。摘要与关键词采用标签段落和内容字符样式。元数据通过 Pandoc 渲染，沿用正文中的链接/脚注定义，保留强调、代码和引用。已解析的真实有序列表保留 Word 编号，代码中的 HTML 不进入表格/图片适配。最终角色传入渲染器，题注与参考文献样式不再被另一套规则覆盖。

## 报告可追溯到源行与输出样式

`normalization-report.json` 使用 `normalized-md/v2` 报告结构；内部 Markdown 仍兼容 `normalized-md/v1` Front Matter。报告包含 changes、decisions、context、counts、metadata、integrity。每个判定包含源行范围、原角色/最终角色、目标 DC_ 样式、处理动作、修改前后、全部候选、加分理由、分差及强度区间；显式 Front Matter 单独记录。报告写入失败返回 processing_warnings，DOCX 仍生成。

生成先写内部候选文件，成功后替换正式 DOCX；失败重试不会覆盖上一份成功文件。原件和首次导入内容不被改写。

## API 迁移不再接受可编辑输入

| 接口 / 字段 | 新契约 |
| --- | --- |
| POST /api/jobs | 上传并导入；返回 ready；suggestions 兼容字段为空 |
| POST /api/jobs/{id}/normalize-and-render | 只接收 style_pack_id / style_pack_version，可发送 `{}` 使用任务样式 |
| source_markdown / confirmed_roles | 已移除；发送旧字段返回 422，调用方应改为修改源文件并新建上传任务 |
| GET /api/jobs/{id}/draft | deprecated，只读返回首次导入内容，用于旧客户端诊断 |
| PUT /api/jobs/{id}/draft | deprecated，返回 410，并提示在源文件或输出 DOCX 中修改 |
| POST /api/jobs/{id}/normalize-docx-direct | 既有接口与 hybrid 默认模式保持 |
| 下载菜单 | DOCX、可选处理报告；不展示中间 Markdown 或样式快照 |

Python normalize_markdown 的 confirmed_roles 参数仅暂留调用签名兼容，自动判定不读取该参数。推荐新调用只传源文本和 filename。

## 样本质量分别衡量正确率与覆盖率

运行：

```bash
uv run python scripts/verify_markdown_scoring.py --output artifacts/markdown-quality
uv run pytest -q
uv run ruff check .
uv run mypy src
npm test --prefix frontend
npm run build --prefix frontend
```

预先按 Issue #1 的中文公文口径标注 3 个合成样本，共 230 项、61 个标题。长报告含 8 章、6 级编号、144 个长正文段，另有明确 Front Matter、小数编号、真实列表、代码、引用、表格、题注与参考文献边界。标注文件独立于分类结果，逐项输出期望/实际角色和源行号。

首轮样本评估为 228/230，角色正确率 99.13%、标题层级正确率 98.36%、自动覆盖率 100%，发现小数编号相对偏移与题名识别问题；修复后该组样本为 230/230，标题层级与自动覆盖率均为 100%，修正项为 0。这只是受控样本结果，不表示所有真实长文档达到 100%。回归质量下限为 98%，无“所有文档百分之百准确”交付门槛。

局部歧义仍可能出现在缺少标签的文前短行、无标点的编号业务句、互相冲突的显式层级，以及依赖未提供图片/附件的 Markdown。Windows 字体替代与复杂页面版式沿用既有运行环境边界。真实业务样本的准确率与人工调整量需要继续用独立标注材料核验。

## 本次验证结果

代码提交 `34bc3f3efccfbaf290706cdcbb7b72010a6af373` 的 [GitHub CI](https://github.com/bronya19c818/doc-converter/actions/runs/38523515338) 全部通过：325 项后端测试通过、2 项环境条件跳过；23 项前端测试通过，Ruff、Mypy、生产构建通过。DOCX 原生 hybrid 验收覆盖 5 个夹具、31 项标注，角色有效格式验收覆盖 20 个案例。仓库已有 11 个 DOCX/PNG 二进制文件 SHA 保持不变。

本地 30 项原生夹具测试因 GitHub 文本接口无法下载二进制而未运行成功；远端使用原件完成上述核验。本地真实 MD、DOC、DOCX 的应用 API 完成导入、生成、PDF 预览和 DOCX 下载。浏览器视觉验收未完成：本地 Chromium 官方下载被截断，云浏览器不能访问此运行环境的 localhost；Vitest 的交互验证不等同于真实浏览器视觉通过。本地没有 CJK 字体，生成 PDF 的中文视觉效果不作验收结论。

## Issue #3 后续优化

第二轮已复用 DOCX-direct 编号序列、章节模型、标题树和源结构恢复。评分、正确修复覆盖率及实际输出核验使用新口径；旧文中的“自动覆盖率”属于 v1 映射率，不能解读为正确修复率。详见 [v2 架构](markdown-auto-normalization-v2-structure-quality.md)、[质量评估](markdown-quality-v2-repair-coverage.md)及[Windows Docker](windows-docker-v2-startup-verification.md)。新规范化输出 schema 为 normalized-md/v2，渲染兼容 v1/v2。
