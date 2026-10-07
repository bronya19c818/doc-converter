# 标题体系、层级压缩与章节树执行记录

起点85420a4，experiment/docx-direct-normalizer。用户最新计划替代“每次局部family随意猜层级”，明确中文理论顺序、仅标题激活、缺层压缩、相对标题、独立数字体系、少量结构reset regimes与章节树。

冻结selector/policy/style_mapper/OOXML/样式页面/DOC/Markdown；不改全局阈值或literal heading原始权重。旧87标签建议不冒称业务确认；新明确示例与原31GT作为用户规范预期，真实问题按规则重新计算，proxy/business-rule-derived/automated三类来源分别记录。

- [x] 新规范DOCX/API反例RED（18项；后补父树返回、数字reset、深层decimal列表、脏Native列表各先RED）
- [x] 客观编号路径、SECTION、relative/reset事实与手工平行序列
- [x] 独立hierarchy_resolver：schemas/regimes/active compression/tree/evidence
- [x] 与加法scoring衔接，保持selector不变与异常保护（36新增API案例及既有压力/语义共68项通过）
- [x] 原31GT、作者/公式、压力及全量检查（后端226、前端26、Ruff/Mypy/build通过）
- [x] 同一11份源、204历史建议对比、新风险候选审核与13問卷（90正文、70层级映射/44保留、13问卷一致；P1代理覆盖540，其中18未决）
- [ ] 整体代码审查、当前HEAD远端CI、main冲突和明确readiness

Pre-flight: heading/list先筛选再激活family；regime/tree结果只提供加法证据，不产生selected decision。native/outline是标题资格与局部父上下文证据，未确认列表不得污染family；保留基线global prior为审计兼容值，不再驱动层级选择。

Ruling: 最新明示层级压缩替代旧草稿中“1.→（一）”任意局部顺序与H4/H5争议标签；旧草稿测试相应改为最新A/B/C/D及数字压缩案例，历史GT提案保持未确认而不覆盖。代价：旧代理建议不再作为正确率分母。

Ruling: 手工列表用连续ordinal/格式平行/无子内容判定，不以办法/标准等关键词定类；真实标题的正文/表格/子标题先提供资格证据。代价：缺正文且无强锚点的特殊编号段可能保留。

Ruling: 有正文但仅一个无锚点普通数字编号不能证明标题；三条相邻操作短项仅尾部挂正文也保留，不激活family。代价：单个孤立短标题可能不自动映射；原边界验收保持通过。

Ruling: 层级证据重分配已有heading likelihood（匹配+40、其他-35），不固定额外堆叠180分；候选分差和全局阈值仍可限制自动接管。代价：相同语法在极高用户阈值下仍会保留。

Ruling: 原生Word大纲为无编号标题提供资格及父/peer线索，实际级别按有效父节点+1或无父为1，均不参与编号层激活。明确Native父容器可开启嵌套regime，并在返回时恢复外层树。代价：污染的源大纲关系仍需警告或代理审核，不能把原生N直接当有效N。

Ruling: 强手工列表与原生Heading矛盾且body低于中阈值时，Resolver报告anchor conflict，利用既有selector保守防线禁止legacy回退。代价：该特殊列表原段样式保留，不重构selector或自动列表编号。

Review closure: 两项仅末项接正文的序列也提供不确定证据；删除全文同家族批量升标题，并以附件/分节/重复章隔离资格统计。新增复现均先RED后GREEN。历史扫描改为每个根体系常量状态；有效层审计区分局部压缩和父偏移。

Real-source closure: 数字根变化退出旧嵌套范围；原生父标题下连续数字子项不提前退出；同原生层级的数字peer不挂到前一个无编号标题下。明确原生父下从1重启的手工标题系列作为独立子体系，在父级peer出现时关闭；子项缺原生样式也保留连续同级关系。无数字父前缀的中文体系decimal不凭路径深度或跨章节旧父节点猜层级，unknown/preserved并报告missing_numbered_parent；超限父不从0重新起算。

Final review closure: 独立数字技术体系同样验证实际前缀父链，缺少1.2时1.2.1不能挂到1.1；1.6S等数字开头业务词保留原生锚点例外。新复现先RED，完整68专项及226后端GREEN。审查修复完成；最终真实源11/11结构和指纹通过，HIGH0，父子倒置0；44旧层级案例仍保留、18新P1未决及其他结构警告须业务确认，不能标成全部修复或真人GT。
