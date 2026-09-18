# DOCX 样式编辑器与双栏工作区设计

## 目标

本项目是一个完全本地运行的 Markdown → DOCX 转换器。转换流程不调用 AI、不上传用户文件，原始 Markdown 永不覆盖。Pandoc 负责内容转换，应用负责规范化、样式模板编译和确定性的 OOXML 收尾；内置浏览器预览只读取本地生成的 DOCX。

## 用户工作流

1. 用户选择 Markdown 文件和一个 DOCX 样式组合。
2. 应用复制源文件到任务目录，创建可编辑的 Markdown 工作副本，并展示确定性结构建议。
3. 左栏编辑工作副本；标题建议可以直接应用为文档标题或副标题。
4. 右栏展示已生成的 DOCX，底部可折叠设置面板负责样式编辑和产物下载。
5. 生成前执行完整性校验；失败时不生成 DOCX，源文件保持不变。

## 规范化中间层

Front Matter 支持 `title`、`subtitle`、`organization`、`department`、`authors` 和 `date`。元数据输出顺序固定为标题、 副标题、单位、部门、作者、日期。单位和部门字段独立保存，但共享 `organization-department` 视觉样式。未确认的建议只作为提示，不阻塞生成；应用动作直接更新工作副本。

## 样式模型

样式包保存 schema 版本和所有固定角色。文字角色通过 `FontSpec` 保存中文字体、西文字体、字号、粗体、斜体和颜色；段落角色通过 `ParagraphSpec` 保存对齐、缩进、间距、行距以及分页控制。样式包采用不可变版本，修改只创建新版本。旧版 `document-title`、`heading-1`、`body` 字段在读取时迁移，缺失角色补齐默认值。

角色包括：`document-title`、`document-subtitle`、`organization-department`、`author`、`date`、`heading-1`、`body-paragraph`、`body-table`、`point`、`table-caption`、`figure-caption`、`footer`、`page`。

## DOCX 输出契约

参考模板生成自包含的 `DC_` 样式：`DC_DocumentTitle`、`DC_DocumentSubtitle`、`DC_OrganizationDepartment`、`DC_Author`、`DC_Date`、`DC_Heading1`、`DC_BodyParagraph`、`DC_TableBody`、`DC_Point`、`DC_TableCaption`、`DC_FigureCaption`、`DC_Footer`。最终语义不依赖系统中已有的 Title、Subtitle、Heading 1 或 Normal。

每个字体同时写入 `w:eastAsia`、`w:ascii`、`w:hAnsi`、`w:cs`。源 Markdown 的全部 H1-H6（文档标题除外）映射到同一个一级标题样式；有序列表编号保留为普通文本并删除 `numPr`；粗体 run 映射到 `DC_Point` 字符样式。标题区按固定元数据顺序插入正文前。页脚使用奇偶页设置，内容为 `－ PAGE －`，奇数页右对齐、偶数页左对齐。

输出文件名使用清理后的文档标题；标题缺失时使用源文件名。Windows 非法字符被替换，路径穿越字符不会进入文件名。

## API 契约

- `POST /api/jobs` 创建任务并立即进入可编辑状态。
- `PUT /api/jobs/{job_id}/draft` 保存工作副本。
- `POST /api/jobs/{job_id}/normalize-and-render` 接收 `source_markdown` 和 `confirmed_roles`，执行校验、规范化、渲染和产物登记。
- `JobRecord` 持有 `output_name`、`draft_updated_at` 和 `source_hash`，产物列表使用实际文件名。

所有产物只能从任务目录读取，下载接口拒绝路径穿越和未登记文件。

## 前端布局

工作区使用 42% / 58% 的左右双栏。左栏包含文件选择、可编辑 Markdown、修改状态和建议应用动作；右栏包含内置 DOCX 预览。完整设置面板固定在页面底部，可展开/折叠，分为标题区角色、一级标题、段落正文、表格正文、要点、图表题、页脚和页面设置。下载 DOCX、规范化 Markdown、审计报告和样式快照只在设置面板显示。窄屏时双栏纵向排列，设置面板仍固定在底部。

## 非目标

不新增模型调用、不自动运行 LibreOffice、不覆盖用户源文件、不使用 Word 自动编号、不把本机已有同名样式作为输出依赖。
