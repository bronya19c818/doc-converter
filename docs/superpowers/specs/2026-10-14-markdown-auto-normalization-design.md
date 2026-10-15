# Issue #1：长文档自动规范化

依据：[Issue #1](https://github.com/bronya19c818/doc-converter/issues/1)，基线 main `8f0820df7e32bc4a4d81aafa8088595ce7c2cdce`。用户明确授权直接实施，不设置阶段确认。

## 产品与接口

保留 MD、DOC、DOCX 输入，选择文件后一次点击开始转换，显示预览并提供 DOCX、可选诊断下载。删除 Markdown 编辑器、建议和确认流程；保留样式及受支持的页面设置。DOCX 默认走已有 hybrid 原生 OOXML 路径。

Markdown/DOC 每次从 `source/imported.md` 重新生成；旧任务无该文件时从原始上传重新导入。GET draft 暂留只读兼容，PUT draft 返回 410；旧 render 的 source_markdown/confirmed_roles 参数返回 422 并说明迁移方式，不静默忽略用户编辑。

## 权威处理链

首次导入 → 内容清理（禁用旧标题推断）→ MarkdownIt 结构与行映射 → 独立 Markdown 特征评分 → 全文编号家族/显式锚点消歧 → 元数据与标题调整 → 样式映射 → 渲染。共享 RoleCandidate/ScoreEvidence/ScoringConfig 的审计模型，不使用 Word 字号和对齐证据，不变更 DOCX 评分实现。

显式 Front Matter 优先，正确 Markdown 标记优先；混合编号依据全文家族和锚点判断，各中文/数字括号层级分别处理。中等强度且有全文证据的候选自动应用，评分是启发式强度。保护代码、表格、引用、链接、图片、脚注与实际列表；参考文献和题注进入角色审计。渲染器不再重新抽取元数据。

## 证据与质量

报告记录源行号、结构类型、特征、全部候选、分差、理由、最终角色及修改前后。回归覆盖元数据、六级标题、复杂编号、正文编号误判、内容边界、DOC 导入、重跑与样式切换。增加人工规则标注的合成长文档样本与可复跑指标脚本，分别报告角色准确率、标题层级正确率、自动覆盖率和修正项；不宣称真实业务文档统计概率或全部文档百分之百正确。
