# DOCX Direct selected decision 实施记录

依据用户提供的九阶段实施计划，在 experiment/docx-direct-normalizer 上原位实施，不合并 main。

## 执行顺序

1. 先写真实 DOCX → API → DOCX/审计验收，读取用户 ground_truth.json。
2. 加入模型、独立 selector、hybrid 默认及 legacy/shadow/scored 回归入口。
3. Mapper 与转换审计仅读取 selected decision；三套结果保持独立。
4. 按样本证据有限补充单位及正文短语上下文，不重建编号、页面或表格。
5. 执行四份样本、原压力文档、边界场景与结构不变性验收。
6. 补 CI、更新架构说明，执行全套检查及独立代码审查。

## 接口与失败模式

- Classifier → Selector：三套 decision 独立，顶层 role/action 仍为 legacy。
- Selector → Mapper：缺失 selected 必须失败关闭；不得隐式读 legacy/scored。
- Mapper → Audit：决策统计与实际执行统计分开，结构安全独立。
- API → Normalizer：模式必须传递、校验并记录，默认 hybrid。
- 可失败方式：高置信接管未执行、歧义回退 legacy、中置信冲突仍映射、弱正则 fallback、列表映射、标题家族层级错误、正文短语升格、审计计数误导、包部件变化、文本顺序变化、原文件覆盖。

## 裁定

- 用户已提供具体架构、样本、计划及验收标准，直接执行已有设计。
- 按项目测试偏好先写端到端验收，不新增 selector 单元测试；已有测试继续全量运行。
- medium 同角色 agreement 保留 scored 的 uncertain 动作；语义角色可确认不代表允许转换。
- 新增回归模式会允许识别证据修正；历史 byte baseline 使用 shadow 模式。
- 样本目录预先存在，保留源文件字节；CodeGraph 索引不纳入提交。

## 验证记录

- 先写端到端验收，初始 8 项均因缺少选择模式失败；实现后专项 14 项通过。
- 修正单位/正文短语上下文后，四份样本共 31 个关键标注全部通过。
- 原压力文档及四模式验证通过；第二轮全量 159 项通过，前端 26 项通过，构建、Ruff、Mypy 通过。
- 用改动前 HEAD 2915a027 的源码采集基线，shadow 的六类输出 ZIP 部件全部一致，六种边界场景通过。
- 四份输出 DOCX 经独立 LibreOffice profile 转 PDF、Poppler 原生程序渲染，7 页已检查；标题/正文坐标核对无重叠。
- 独立 code-reviewer 与 python-reviewer 找到两处 Important：全保留仍序列化 document.xml、验收可能漏过 mapped 未执行。两处均用真实转换先复现 RED，再修复 GREEN；专项增至 16 项通过，无未处理 Minor。
- 新增 CI 已做 YAML 语法校验；尚未推送，不能宣称 GitHub 运行通过。
- 最终全量 161 项通过（仅依赖弃用警告），Ruff、Mypy 通过；前端 26 项与构建通过。最终 hybrid 四份样本+压力、31 条 GT、6 种边界及 shadow 六类历史基线全部通过。工件保存在 artifacts/selected-decision/final-acceptance 和 final-shadow。
