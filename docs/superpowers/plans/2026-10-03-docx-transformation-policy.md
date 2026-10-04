# DOCX Direct 第二阶段转换策略实施计划

目标：按用户本阶段完整要求，使用 legacy role 解析显式 TransformationPolicy，统一基础视觉格式并保留语义格式和 OOXML 结构。scored classifier 继续 legacy-with-shadow。

架构：策略族集中在 transformation_policy.py；formatting.py 分段落/字符执行；style_mapper.py 解析策略、收集安全性和属性审计。必要时给源字符样式增加按策略过滤的副本，保留原样式，避免字符样式字体/字号覆盖目标段落样式。normalizer 原位写回 document/styles 两个部件，不重建内容。

## 约束与失败方式

- 不改评分、API/UI、Markdown、DOC、页面、分节、表格/编号/脚注尾注重建。
- 标题局部视觉格式或字符样式可能压过目标样式：强覆盖清除字体/字号/粗斜体/颜色覆盖，保留上下标和结构。
- 正文局部粗斜体可能误当全段格式：仅全段直接属性一致时清除；局部或受保护文本存在时保留。
- 源字符样式可能继承异常字体/字号：按策略派生字符样式，不删除 rStyle 语义，不改原样式及未映射段落。
- 域结果、修订、脚注标记、图形、公式可能被普通 run 清理误伤：这些区域不进入普通字符清理。
- numPr 相关缩进、表格合并/尺寸/嵌套结构、链接/书签/换行/分页可能丢失：禁止重建结构，编号缩进默认保留。
- 审计可能只写预期而非实际：记录每段实际 policy、safe/guarded/preserve、属性数量和原因，并核对 ZIP 结构。

## 执行任务

- [x] 先写策略解析专项测试及完整 DOCX 转换测试：标题强覆盖、正文混合、字符样式继承、表格/编号缩进、复杂结构与未映射原样；先验证失败。
- [x] 新增四个不可变策略族与绝对保留结构清单；扩展实际策略审计模型。
- [x] 将 formatting.py 拆成显式段落与 run 执行器，保留旧 clean_uniform_direct_formatting 兼容入口。
- [x] 将字符样式过滤独立实现，原样式不修改；在 normalizer 中原位提交新增 styles 和 document。
- [x] style_mapper 按 legacy role 解析策略，给每个元素记录转换结果；audit 添加实际策略审计。
- [x] 新增可复跑策略压力脚本；shadow 脚本保留原严格模式，额外支持第二阶段输出部件允许改变但源/legacy/scored 保持一致的验证。
- [x] 跑专项、现有 Direct/压力/主路线回归、shadow 验证、Ruff/Mypy；按 requesting-code-review 技能安排只读审查并修复。
- [x] 选生成的复杂 DOCX、真实压力文档与两份业务文档，使用 soffice.com 独立配置渲染 PDF，直接调用 Poppler 原生程序检查页面图片。

验收记录：`artifacts/policy-verified-20261003/acceptance.md`。最终 143 后端测试、静态检查、默认严格模式及第一阶段影子对比通过；独立审查未发现未修复 P1/P2。视觉检查记录 6S 文档 20→30 页及大表格行不拆分产生的表头单页；未执行 Microsoft Word 人工操作验收。
