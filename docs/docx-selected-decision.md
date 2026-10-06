# DOCX Direct 决策选择与发布模式

实际链路为 `Analyzer → Feature Extractor → Scoring / Resolver → scored_decision → Decision Selector → selected_decision → Transformation Policy → DOCX`。

`decision_selector.py` 只选择语义、置信强度、动作与来源，不读写 OOXML，不决定转换安全。Mapper 只读取 `selected_decision.role / action`，缺失 selected 会拒绝转换。`safe / guarded / preserve` 由转换策略执行时独立判定。

## 模式

| 模式 | selected 来源 | 使用场景 |
| --- | --- | --- |
| hybrid（默认） | 保守选择 scored、agreement、legacy 或 preserve | 正常直接规范化 |
| legacy | legacy 独立副本 | 历史输出回归 |
| shadow | legacy 独立副本，同时记录 scored | 影子对照与历史输出回归 |
| scored | scored 独立副本 | 实验全接管 |

四种模式均保留三套判定。元素顶层 `role / confidence / action / reasons / region` 仍为 legacy，独立全文区域在 `features.region`。`classification_mode` 记录本次选择模式。

`classify_document` 和 `normalize_docx_direct` 接受 `decision_mode` 及可选 `scoring_config`。HTTP `POST /api/jobs/{id}/normalize-docx-direct` 接受 `decision_mode`，未传时 hybrid，不合法值返回 422；前端使用默认值。

## hybrid 规则

1. Resolver 层级跳跃/编号锚点冲突、分差低于歧义阈值：preserve，禁止 legacy 回退。风险否决优先于一般 agreement。
2. legacy 与 scored 的角色、动作一致：选择 scored 副本，来源 agreement。
3. scored 为 mapped、高置信、分数及分差同时达阈值：来源 scored，可覆盖 legacy。
4. scored 中置信且与 legacy mapped 同角色：agreement，保留 scored uncertain 动作，不升为 mapped。
5. 中置信冲突：保留 scored 角色，动作 preserved，来源 preserve。
6. 无有效 scored 候选时，只允许原生 Heading、明确文前标签/日期、表格位置、题注及参考文献边界等强锚点回退。自动列表、复杂对象、scored unknown 的结构判断和普通编号正则不能回退。

选择结果为独立副本，不修改两套原判定。`selection_source / selection_reason` 可审计，保留动作不代表语义角色必须 unknown。

## 有限校准

保留全文编号家族及数字深度推断。机构后缀补充“公司…部/处”，并在题名后、日期前的文前组合中增加上下文证据。正文常见样式短语夹在两段完整正文句之间，且没有编号、元数据、题注或复杂对象证据时，增加正文证据，避免仅按字号误判题名。所有贡献记录在 additive evidence。

## 审计

- `classification.legacy_counts / scored_counts / selected_counts` 分别统计判定动作。
- `legacy_scored_disagreements / scored_selected_disagreements` 统计角色或动作不同的段落数。
- 每段记录三套 decision、selection 来源/原因、policy、transform_safety 及属性处理。record 的 `detected_role / confidence / action` 表示 selected。
- `counts / xml_patch` 表示实际执行：mapped 为已执行数；uncertain、preserved 为所选动作未执行；skipped 为 selected mapped 但因样式、策略、节点或结构安全而跳过。合计与元素数一致。
- `target_style` 是 selected mapped 的计划目标，是否执行结合 `modified_element_ids / transform_safety` 判断。

## 可复跑验收

```powershell
uv run python scripts/verify_docx_shadow.py --decision-mode hybrid --output artifacts/selected-acceptance-new
uv run python scripts/verify_docx_shadow.py --decision-mode legacy --acceptance --output artifacts/legacy-acceptance-new
uv run python scripts/verify_docx_shadow.py --decision-mode scored --acceptance --output artifacts/scored-experiment-new
```

每次指定新目录。脚本读取用户 ground_truth.json，通过真实 API 上传、转换、下载四份样本及压力文档，保存 DOCX、审计及 verification.json。hybrid 强制关键标注全部通过；其他模式保留比较结果、验证结构，不要求历史分类器正确。

检查可见文本/段落顺序、源 SHA256、全部 ZIP member（仅 document/styles 允许变化）、原有样式定义、超链接关系、编号、页眉页脚、分页、上下标、网格和横纵合并。selected 非 mapped 的段落须 canonical XML 一致；没有实际映射时整个 document.xml 必须 byte-identical，不重新序列化。mapped 已执行段落必须有执行 ID 和真实目标样式；未执行必须有独立安全审计，且 skipped 计数逐段对得上。关键结构角色的 ground truth 同时要求实际执行。可添加 `--edge-cases` 验证孤立编号、手工操作清单、无标题短语、左对齐题名及副标题边界。

历史基线使用 `--decision-mode shadow --baseline ... --output ... --edge-cases`。`--policy-output` 仍支持第二阶段历史策略核对，须使用同版本评分证据；本阶段有意校准 scored，不能要求不同识别版本的分数相等。

CI 执行全套 pytest、ruff、mypy、frontend tests/build 与专项验收，即使失败也上传产物。Windows LibreOffice/Poppler 视觉检查保留本地执行；新增 workflow 不代表尚未运行的远程 HEAD 全绿。

本阶段不重建编号、页面、表格、页眉页脚，不删除 legacy，不合并 main。
