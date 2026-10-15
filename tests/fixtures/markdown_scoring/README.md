# Markdown 评分验收样本

`ground_truth.json` 的角色/层级依据 Issue #1 的中文公文层级口径与明确 Markdown 结构预先标注，不从分类器结果生成。样本为公开可复跑的合成材料，不含客户文档，不代表真实业务文档总体准确率。

- long_report.md：8 个章节、6 级编号、144 个长正文段，覆盖全文重复起号与文前信息。
- mixed_boundaries.md：显式锚点、小数编号、正文编号句、代码/列表/引用/表格、参考文献和题注。
- front_matter.md：显式元数据、不同标题层级及正文。

运行 `uv run python scripts/verify_markdown_scoring.py --output artifacts/markdown-quality`。指标按预先标注项统计角色准确率、标题层级正确率、自动处理覆盖率与需要修正的项数；逐项输出期望/实际角色与源行号。不能用“自动应用”代替“正确”。
