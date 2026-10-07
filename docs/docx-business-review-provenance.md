# DOCX业务审核来源与结构收口

`scripts/reconcile_docx_business_review.py` 是离线审核工具：读取已生成的11源API工件、具体GT、用户确认规则、旧pending与可选代理审核；不被转换器调用，不修改Word或生产算法，不把审核数据作为运行依赖。

## 来源

| 来源 | 含义 | 验收边界 |
|---|---|---|
| user_confirmed_element | 用户点名的具体源ID | 保留严格GT及两个允许结果各自口径 |
| user_confirmed_rule | 用户确认业务结构规则 | 规则独立保存确认引用和SHA，不冒充逐元素签署 |
| business_structure_derived | 完整源结构匹配后由规则推出的实例 | 记录真实源、根、Regime、前后边界、编号关系与证据ID |
| proxy_review | 代理建议或上下文比较 | 不作业务真值；低优先级待审单列 |
| automated_inference | 只有当前分析或树假设 | 树自洽不能生成用户确认 |

`proposal_status=active/superseded` 只描述旧代理建议。被确认规则取代的H2建议保留为历史值，当前建议不再显示它。当前selected、业务预期、推导来源和实际XML执行分别记录。

## 规则签名

技术规范的服务结构须同时满足：相同源SHA；实际CN父标题身份；存在唯一未编号`服务内容`实体；后续中文括号第二节边界；完整七个主题且顺序一致；原始1.x/3.x正文前缀和2.1/2.2、4.1～4.7子主题系列一致；匹配目标处于同一Regime，且没有跨分节/附件。预期来自用户规则的H2/H3/H4，不能从selected或recovered路径复制。文字相同但父、Regime、前缀或子系列不同的反例不推导。

设施设备规程以用户具体8.1～8.3 H4为锚点，核对实际8主题、父绑定、完整1～8源编号和同级源样式后推出H3。九章只有收到独立用户规则后才应用，不通过七章规则自动扩大范围。

用户最终确认九章源文件混用“一、（一）、1.”和“一、1.”，1～11采用H3、11.1～11.4采用H4。该确认替代之前的H2选择，原42条具体GT保持不变。当前内部虚拟H2仍为自动结构假设/技术层级占位；不能据此宣称用户确认源中漏写了一个真实H2标题。审核记录保存业务解释与自动source_defect_type各自来源。

只有源签名通过、当前角色/动作匹配、确认父关系匹配且报告包含实际XML修改ID，才能关闭对应映射项。未知保留不算规则映射成功。没有覆盖的结构组或映射差异继续业务pending，旧样本代理待审不混入业务阻塞数量。

## 使用

```powershell
uv run python scripts/reconcile_docx_business_review.py `
  --cohort <本地11源验收目录> `
  --ground-truth artifacts/source-structure-gt/user-confirmed-ground-truth.json `
  --rules <用户确认规则JSON> `
  --previous <上一轮pending-business-ground-truth.json> `
  --proxy-review <上一轮review-decisions.json> `
  --output <本轮审核目录>
```

工件为business-review.json及按结构问题分组的pending-business-ground-truth.json/md。确认引用必须是可读取的本地材料，程序实际核对内容SHA；它证明材料一致性，不代替人工确认来源的转录责任。具体GT与规则的角色、动作及已指定父关系分别保留，冲突或重复源身份时拒绝生成结果。case目录必须位于指定cohort中；指纹、源ID不一致同样拒绝。映射不满足确认规则时输出差异并返回失败。所有真实源、具体GT、规则引用和私有审核工件留在artifacts，不进入Git。

本阶段本地对照：原89条/24组；先吸收服务与设施两规则后剩九章11条/1组；吸收最终九章确认后为0条/0组。三条规则匹配八个章节实例，100条结构推导（不含具体GT）、42严格GT与2允许结果分别验收；19条旧建议superseded，75条低优先级代理未决继续单列。数量不是目标，完整来源与可重复核验才是关闭依据。
