# DOCX业务审核收口执行记录

起点f0e9e6a，沿用experiment/docx-direct-normalizer与现有私有11源验收；保留.codegraph和既有工件。

- [x] 提取用户业务规则并固定证据来源；42严格GT和2允许结果保持不可变。
- [x] 审核CLI的实际DOCX/API→结构规则→分组审核端到端反例先RED；包括文字相同但父/Regime/前缀/子系列不同、GT/源指纹冲突、九章不自动推广。
- [x] 只新增离线审核工具及来源字段；技术规范完整签名匹配、七章由8.x GT/稳定同级关系推导、旧建议superseded。
- [x] 89条旧pending逐条核对；重复案例归入规则推导，剩余按真正结构问题分组，低优先级代理另列。
- [x] 收到九章业务确认后决定是否需要算法变更；未回答或暂缓时保持pending，不以默认选项当作确认。
- [x] 42GT/规则推导/44历史/114反例/90依据/问卷13/11源/全量本地验证。
- [ ] 最终HEAD CI与merge-readiness由提交后的外部验收工件记录，不以本记录的提交时状态替代。

Ruling: 用户已给出完整审核设计，按executing-plans与ponytail执行，不扩充生产分类器。公开scripts工具负责可复验审核；真实源、GT、确认规则、审核快照仍留artifacts。所有src生产代码冻结，只有业务确认暴露不能表达的真实结构时才另行处理。

Pre-flight: user_confirmed_element是严格具体ID；user_confirmed_rule是有证据参考的规则记录；business_structure_derived必须匹配完整源签名，不能从selected/effective直接造预期。代理proposal_status与实际映射验证分别记录；只有真实成功映射和完整签名才能关闭相应旧pending。

Ruling: 九章虽然已有11.x严格GT，本次用户明确要求其父层结构继续业务未决，不自动用七章规则推广。已询问A直达H2、B遗漏H2后H3或暂缓；未答前完成独立审核工具工作，不执行任何依赖业务答案的修改。

Ruling: 用户最终说明两套源编号混用、业务内容不足以单列（一），明确九章1～11使用H3、11.1～11.4使用H4；该文本取代先前A选择。42严格GT不修订。九章虚拟H2仍是自动内部占位，不冒充用户确认缺失真实源标题；生产算法已能表达当前要求，无需变更。

Evidence: 初始7个CLI端到端失败先RED，再实现审核工具；低优先级代理输入先8失败再GREEN。审查确认引用缺校验、case越界、相同角色但父/动作冲突、重复身份覆盖；4+6条实际DOCX/API→CLI拒绝反例先RED。引用文件及SHA实际读取校验、来源类型、完整预期、目录范围和唯一身份均落实，11.4补入四锚点。18条端到端全部GREEN，Ruff与src+审核CLI的Mypy通过。

Evidence: 2条原规则先关闭78旧pending，留下九章1组11项；3条最终规则匹配8个结构实例，共100条business_structure_derived，关闭全部89旧pending，严格42及允许2仍独立核验，19旧建议superseded。75低优先级代理待审另列；不是以pending数量做正确率。最终11源重新生成，独立核对实际Word标题样式与历史反例。

Final verification is recorded in artifacts/business-rule-review/final-validated (reviewed full suite, source/style/cohort hashes, finalHEAD CI and merge-readiness). Keep original iterations and private confirmation data local. Only scripts/tests/docs are staged; every src blob remains identical to f0e9e6a. No main merge authorized.

Final local results: reviewed backend267 passed (privateGT included), frontend26/build, Ruff/Mypy src+CLI passed. Fresh11 sources/12192 elements preserved, all ZIP part payloads identical to f0e9e6a; 142 actual Word heading styles verified (42 strict+100 derived). Historical44 now10 user_confirmed_element+34 business_structure_derived;114/90/13 and31 acceptance/6author-formula all pass. Production source blobs frozen.75 low priority proxy pending retained separately. Final CI must match the later commit HEAD before claimingREADY.
