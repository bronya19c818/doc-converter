# DOCX 样式编辑器与 A4 工作区设计说明

## 目标

在保持“本机、确定性、无 AI、原始 Markdown 不覆盖”的前提下，补齐中文正式文档常用的标题区元数据识别、摘要/关键词样式、自包含 DOCX 样式、悬浮设置面板和 A4 纸张预览。

## 非目标

- 不引入 AI 推断、云端上传或远程文档服务。
- 不把普通正文强制改写为摘要、副标题或关键词。
- 不使用 LibreOffice 作为自动转换链路；它只保留为用户下载后的外部兼容工具。
- 不通过裁剪内容模拟分页；预览必须使用 DOCX 的页面尺寸和 `docx-preview` 的 wrapper。

## 数据与识别

### 元数据模型

规范化 Front Matter 的字段顺序固定为：

1. `title`
2. `subtitle`
3. `organization`
4. `department`
5. `authors`
6. `date`
7. `abstract`
8. `keywords`

`abstract` 使用字符串，`keywords` 使用字符串数组。Front Matter 明确填写的字段优先于正文识别结果。工作区结构建议支持将标题区候选直接应用为 `title`、`subtitle`、`abstract`、`keywords`、`authors`、`organization`、`department` 和 `date`；应用动作必须更新 Markdown 工作副本，而不是只在渲染请求中携带一次性确认值。

### 正文识别规则

规范化器在移除 Front Matter 后，只检查文档开头、首个标题/表格/代码块之前的非空块：

- 已有 `title` 且没有 `subtitle` 时，识别第一条单行、长度不超过 80 个字符、不是标题/列表/表格/代码块、不是“摘要/关键词”标签且不以常见句末标点结束的短文本为副标题。
- 识别 `摘要：`、`摘要:`、`关键词：`、`关键词:` 前缀。摘要保留为字符串；关键词按 `；`、`;`、`，`、`,`、换行拆分并去除空项。
- 标题区附近的 `作者：`、`作者单位：`、`单位：`、`部门：` 等显式标签优先；无标签时，对标题后的 2—4 字常见中文姓名和不超过 20 字、含“公司/中心/部/处/科/室”等关键词的短行做保守识别。
- 简单原始 HTML `<table>` 在交给 Pandoc 前转换为 Markdown 表格；表格前以“表1”“表一”等开头的单行保留为表题，不参与副标题识别。
- 已存在对应 Front Matter 时，不再移动正文中的同类内容。
- 被识别的块从交给 Pandoc 的正文中移除，并在规范化报告中记录 `from`、`to` 和 `line`。
- 其他文本、图片、链接、表格和代码块保持不变；完整性校验继续比较图片和链接集合。

## DOCX 样式

新增六个标题区角色：

| 角色 | Word 样式 ID | 默认语义 |
| --- | --- | --- |
| `abstract-label` | `DC_AbstractLabel` | 摘要： |
| `abstract-content` | `DC_AbstractContent` | 摘要内容字符 |
| `abstract` | `DC_Abstract` | 摘要内容段落 |
| `keywords-label` | `DC_KeywordsLabel` | 关键词： |
| `keywords-content` | `DC_KeywordsContent` | 关键词内容字符 |
| `keywords` | `DC_Keywords` | 关键词内容段落 |

六个角色进入“标题区角色”分组；标签和内容角色为字符样式，只编辑字体属性，摘要和关键词段落角色继续编辑对齐、缩进、行距和段前/段后。默认值分别复制段落正文的中文正式文档基线，关键词首行缩进为 0。

所有页面默认使用 A4：宽 21.0 cm，高 29.7 cm；页边距保持现有 3.5/3.5/2.8/2.8 cm。A4 尺寸写入生成 DOCX 的 section，同时由预览工作台显示为独立白色纸张。

## 元数据输出

OOXML 收尾层在正文前按固定顺序插入标题区：标题、副标题、单位、部门、作者、日期、摘要、关键词。单位和部门继续共用 `DC_OrganizationDepartment`；作者数组用“、”连接。摘要和关键词段落分别使用 `DC_Abstract` 与 `DC_Keywords`，标签运行分别使用 `DC_AbstractLabel` / `DC_KeywordsLabel`，内容运行分别使用 `DC_AbstractContent` / `DC_KeywordsContent`。

## 前端工作区

- 左右工作区继续保持 42%/58%。
- 设置面板从文档流中移出，默认折叠。
- 折叠时显示固定在右下角的“⚙ 设置”悬浮按钮；展开后面板固定在底部，内部滚动，关闭按钮始终可见。
- 面板标签为“样式角色”“页面设置”“下载产物”。生成按钮位于面板标题栏，下载链接只出现在产物标签。
- 移动端面板宽度占满视口底部，工作区纵向排列。

## 内置预览

`DocxPreview` 使用 `docx-preview` 的 `inWrapper: true`、`breakPages: true`、页眉页脚渲染和 `ignoreLastRenderedPageBreak: false`。预览区是可独立滚动的灰绿色工作台，wrapper 内的每个页面按 A4 尺寸居中、留白、带轻阴影；不使用连续无纸张的长页面样式。

## 测试夹具

测试使用项目自生成的综合 Markdown，不依赖用户本地文件。夹具覆盖：Front Matter、自动副标题、摘要、关键词、多级标题、有序/无序列表、粗体、链接、图片、表格、代码块和中文/西文混排。测试只验证确定性结果、OOXML 样式 ID、A4 section 属性、预览渲染选项和可访问的前端交互。

## 验收标准

- 截图中的标题后短句能识别为副标题并出现在 `DC_DocumentSubtitle` 段落。
- 摘要和关键词不会进入正文重复输出，且可分别通过 `DC_Abstract`、`DC_Keywords` 定位。
- 原始 HTML 表格会生成可编辑 DOCX 表格，表题段落使用 `DC_TableCaption`，单元格段落使用 `DC_TableBody`。
- 新旧样式包均能读取；旧包补齐新角色并保持旧值，保存时仍生成不可变新版本。
- 输出 DOCX 的 section 为 A4，`styles.xml` 含摘要/关键词标签与内容角色、`DC_TableCaption`、`DC_TableBody` 和既有 `DC_` 样式。
- 设置面板无需滚动到底部即可打开、切换标签和收起；默认状态为折叠。
- 预览启用 wrapper 分页，A4 纸张显示为分开的白色页面。
- Python 测试、前端测试、Ruff、Mypy、前端构建全部通过。
