# DOCX Direct 第二阶段执行记录

基线88225808da9cc255790468db364f99f76922a2a1，experiment/docx-direct-normalizer；用户设计与35节实施计划为本轮依据。沿用已验证的实验checkout，保留.codegraph和私有材料；不另建实现任务。

- [x] Role Capability Matrix：StylePack、自动识别、段落/字符执行和supported/preserve-only/out-of-scope逐项声明。
- [x] 实际DOCX端到端契约先RED：dirtyH6→H3、dirtyHeading作者→无标题outline，基础字体/分页覆盖、局部强调/字符投影、复杂结构与表格编号保护。
- [x] 分离角色策略；mapped角色接管outline/widow/pageBreak等视觉属性，Preserver只物化真正结构；保留manual br、numPr及编号ind。
- [x] 摘要/关键词明确标签的inline segments与安全Run split，显式tblHeader列头接口闭环；不猜第一行/第一列，不扩展标题推断。
- [x] 应用托管样式安全upsert，A→A、A→B、B→B、派生字符样式幂等；非托管源样式不改。
- [x] 输出重新analyze，核对实际有效格式和outline并记录逐项应用/保护状态，不能只看样式ID。
- [x] 同11真实源、42严格+100规则推导、44/114/90/13、6作者公式、31原GT、全量与代表页重新渲染。
- [x] 一次整体审查与修复，分阶段提交；本地全部验收通过。

最终HEAD的CI、main冲突检查与合并结果写入私有验收目录的final-readiness.json及验收报告.md；只有全部merge gate通过才合并main。此记录随实现提交，不将尚未发生的CI或合并记为完成。

Pre-flight: 识别→selected role不在Transformation层重判；StylePack显式配置→编译DC目标→安全执行→输出analyze/audit。源编号/对象/表格部件与可见文本作为独立不变量。现有政策测试对outline/pageBreakBefore保留和只insert样式的旧断言须在实现前更新为用户明确的新契约。

Ruling: 用户已提供完整书面设计和执行顺序，按executing-plans/ponytail/TDD直接实施，不重复请求设计批准；既有实验分支满足用户指定隔离范围，不创建额外worktree。最终合并已获得本轮条件授权，只在全部验收通过后执行。

Ruling: 旧memory中的分页属性全保留是阶段一边界，已被本轮用户明确的mapped段落pageBreakBefore/widow/outline控制取代；手工分页、section/table和numPr继续绝对保护。

Ruling: 默认冻结features/scoring/manual-sequence/hierarchy/source-recovery/selector。新metadata inline和tblHeader需要最小Analyzer/Classifier接口补齐；在明确标签/OOXML证据上独立标注，不修改既有评分阈值、标题体系或业务GT。

审查闭环：域节点字节保护扩展到源有效格式保护；换pStyle/upsert影响受保护片段时保留段落/定义，后验再次比源验证。Math/OLE基线覆盖全部普通/复杂字体键。default=true编号保护、preserve-only托管定义更新、bCs/iCs核验、rebase逐层移除计数和CLI类型问题已修复。两位只读审查员复核关闭全部行为问题。

字体实检闭环：实际DOCX EA仿宋正确，但原LO预览曾误用MS-UIGothic；对同一文件独立profile同字体别名映射后实际PDF使用FangSong，保留DOCX及fontTable所有字节。追加真实upload/normalize/download/PDF字体E2E，验证只有FangSong；Windows字体依赖在CI明示skip。

预览路径实检：Office使用独立短临时目录和英文文件名副本；PDF在目标目录暂存、关闭后原子发布，覆盖深路径及系统临时目录与任务目录跨盘的情形。最终后端286项全部通过（含本地GT与真实PDF字体检查），前端26项通过，Ruff/Mypy/build通过；独立跨盘PDF验收另保存工件。

证据：artifacts/role-v2/acceptance-accepted的20组角色实际DOCX工件；final-accepted的11源/12192元素、42严格/100推导、142实际标题样式和outline、44/114/90/13历史回归及0受控格式差异；font-api-final字体验收；visual-correct-fonts代表页(技术1/3/4/13，论文1/2，问卷1/2)，技术90页/论文8页/问卷10页。没有声称全页人工检查，保留既有表格分页边界和75低优先代理样本。
