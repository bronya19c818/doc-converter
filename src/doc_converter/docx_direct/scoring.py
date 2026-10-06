"""Independent additive role scores and configurable decision thresholds."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doc_converter.docx_direct.model import (
    Action,
    ClassificationDecision,
    RoleCandidate,
    ScoreEvidence,
)

ROLES = (
    "document-title", "document-subtitle", "organization-department", "author", "date",
    *(f"heading-{i}" for i in range(1, 7)),
    "body-paragraph", "body-table", "table-caption", "figure-caption",
    "reference-heading", "reference-entry", "unknown",
)


class ScoringConfig(BaseModel):
    """Heuristic settings, separate from style-pack and legacy mapping policy."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    high_score: float = Field(default=85, ge=0)
    medium_score: float = Field(default=65, ge=0)
    high_margin: float = Field(default=15, gt=0)
    ambiguous_margin: float = Field(default=5, ge=0)
    larger_font_ratio: float = Field(default=1.2, gt=1)
    body_font_tolerance: float = Field(default=0.12, ge=0, lt=1)
    # Overrides allow sample-driven tuning without editing rule code.
    weights: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_thresholds(self) -> ScoringConfig:
        if self.medium_score > self.high_score:
            raise ValueError("medium_score 不能大于 high_score")
        if self.ambiguous_margin > self.high_margin:
            raise ValueError("ambiguous_margin 不能大于 high_margin")
        return self


def contribute(
    candidate: RoleCandidate, config: ScoringConfig, feature: str,
    default: float, reason: str, *, context: bool = False,
) -> None:
    """Keep scores exactly reproducible by summing their evidence."""

    value = config.weights.get(feature, default)
    candidate.evidence.append(ScoreEvidence(
        feature=feature, contribution=value, reason=reason,
        stage="context" if context else "raw",
    ))
    if not context:
        candidate.raw_score += value
    candidate.resolved_score += value


def score_roles(features: dict[str, Any], config: ScoringConfig) -> list[RoleCandidate]:
    f = features
    candidates = [RoleCandidate(role=role) for role in ROLES]
    short = f["short_text"]
    ratio = f["font_size_to_body_ratio"]
    large = ratio is not None and ratio >= config.larger_font_ratio
    near_body = ratio is not None and abs(ratio - 1) <= config.body_font_tolerance
    centered = f["alignment"] == "center"
    early = f["document_order"] < 12
    metadata = any(f[k] for k in ("explicit_author_label", "explicit_organization_label", "explicit_date", "person_name_pattern", "organization_pattern", "author_name_list_pattern"))
    for candidate in candidates:
        role = candidate.role

        def add(key: str, points: float, reason: str) -> None:
            contribute(candidate, config, key, points, reason)

        add("prior", 0, "候选独立从零开始，未命中特征不产生隐含加分")
        if role.startswith("heading-"):
            level = int(role[-1])
            native = f["native_heading_level"]
            outline = f["outline_level"]
            if native:
                add("native_heading_match" if native == level else "native_heading_other",
                    95 if native == level else -45, f"原生标题层级为 {native}")
            if isinstance(outline, int) and 0 <= outline <= 5:
                if outline + 1 == level:
                    add("inherited_outline" if f["based_on_heading"] and not native else "outline_match",
                        15 if f["based_on_heading"] and not native else 35,
                        "有效大纲级别匹配；仅继承标题样式时降低证据强度")
                else:
                    add("outline_other", -25, "有效大纲级别属于另一标题候选")
            if f["numbering_family"]:
                add("literal_heading_number", 35, f"检测到 {f['numbering_family']} 编号，家族层级待全文判断")
                depth = f["numbering_depth"]
                if depth:
                    add("decimal_depth_match" if depth == level else "decimal_depth_other",
                        45 if depth == level else -35, f"数字编号共有 {depth} 层")
            if short:
                add("heading_short", 15, "独立短文本符合标题长度特征")
            if f["text_length"] and not f["has_terminal_punctuation"]:
                add("heading_no_terminal", 10, "无正文句末标点")
            if large:
                add("heading_large_font", 12, "主导字号明显大于正文基线")
            if f["dominant_bold"]:
                add("heading_bold", 6, "主导文字为粗体")
            if f["keep_next"]:
                add("heading_keep_next", 6, "段落具有与下段同页属性")
            if f["page_break_before"]:
                add("heading_page_break", 4, "段前分页提供弱结构证据")
            if f["table_context"] is not None:
                add("heading_in_table", -120, "表格单元格内容不能升格为全文标题")
            if f["body_sentence"]:
                add("heading_body_sentence", -110, "完整正文句与标题冲突")
            if f["text_length"] > 80:
                add("heading_long_text", -65, "长段落与独立标题冲突")
            if f["list"]:
                add("heading_automatic_list", -100, "自动列表保留列表语义")
            if metadata or f["caption_pattern"] or f["reference_boundary"]:
                add("heading_other_content", -70, "明确元数据、题注或参考文献边界与普通标题冲突")
        elif role == "body-paragraph":
            if f["text_length"]:
                add("body_nonempty", 20, "非空文字提供基本正文证据")
            if near_body:
                add("body_font", 15, "主导字号接近正文主体字号")
            if f["common_body_style"]:
                add("body_style", 20, "使用全文正文常见样式")
            if f["common_body_alignment"]:
                add("body_alignment", 5, "对齐方式与常见正文一致")
            if f["body_sentence"]:
                add("body_complete_sentence", 35, "具有正常句末标点的完整句")
            if f["text_length"] >= 20:
                add("body_length", 10, "文本长度提供正文证据")
            if f["numbering_family"] and not f["body_sentence"]:
                add("body_heading_number", -35, "短编号文本与普通正文竞争")
            if f["native_heading_level"]:
                add("body_native_heading", -55, "原生标题样式与正文冲突")
            if isinstance(f["outline_level"], int) and 0 <= f["outline_level"] <= 5 and not f["body_sentence"]:
                add("body_outline", -30, "标题大纲级别与正文冲突")
            if centered and large:
                add("body_centered_large", -35, "居中大字号与正文冲突")
            if f["table_context"] is not None:
                add("body_table_conflict", -100, "位于表格内部")
            if metadata or f["caption_pattern"] or f["reference_boundary"]:
                add("body_other_content", -65, "专门内容角色证据与普通正文冲突")
            if f["list"]:
                add("body_list", -80, "自动列表不可按普通正文处理")
        elif role == "body-table":
            add("table_location", 105 if f["table_context"] is not None else -80,
                "表格上下文存在" if f["table_context"] is not None else "不在表格内")
            if f["text_length"]:
                add("table_nonempty", 10, "非空表内文本")
        elif role in {"document-title", "document-subtitle"}:
            native_title = f["native_title_style"]
            expected_style = "title" if role == "document-title" else "subtitle"
            if native_title:
                add("native_title_style_match" if native_title == expected_style else "native_title_style_other",
                    60 if native_title == expected_style else -30, "Word 原生文档标题/副标题样式证据")
            if not centered and not native_title and not large:
                add("title_without_layout", -40, "缺少居中、原生文档标题或明显大于正文的主导字号证据")
            if early:
                add("title_early", 10, "位于文档开始的十二段内")
            else:
                add("title_late", -60, "远离文前区域")
            if short:
                add("title_short", 15, "短文本符合文前标题长度")
            if centered:
                add("title_centered", 20, "有效格式为居中")
            if large:
                add("title_large", 20, "主导字号明显高于正文")
            if f["largest_preface_size"] and (large or native_title):
                add("title_largest" if role == "document-title" else "subtitle_largest",
                    20 if role == "document-title" else -15, "是文前最大主导字号")
            elif role == "document-subtitle" and centered:
                add("subtitle_smaller", 10, "居中且字号小于文前最大值")
            if f["body_sentence"] or f["text_length"] > 80:
                add("title_body_sentence", -100, "正文长句与文前标题冲突")
            if metadata or f["numbering_family"] or f["native_heading_level"] or f["caption_pattern"]:
                add("title_other_content", -80, "元数据、编号、原生章节标题或题注证据")
        elif role in {"author", "organization-department", "date"}:
            label = {"author": "explicit_author_label", "organization-department": "explicit_organization_label", "date": "explicit_date"}[role]
            if f[label]:
                add(label, 75, "明确标签或日期格式提供强证据")
            elif role == "author" and f["person_name_pattern"]:
                add("person_name_pattern", 35, "纯姓名形式为弱证据")
            elif role == "author" and f["author_name_list_pattern"]:
                add("author_name_list_pattern", 45, "多个中文姓名为作者候选，须有题名后上下文印证")
            elif role == "organization-department" and f["organization_pattern"]:
                add("organization_pattern", 45, "机构名称后缀为弱证据")
            else:
                add("metadata_absent", -45, "没有相应元数据文本证据")
            if early:
                add("metadata_early", 5, "处于文档开头")
            if f["body_sentence"]:
                add("metadata_sentence", -70, "完整正文句与独立元数据冲突")
        elif role in {"table-caption", "figure-caption"}:
            expected = {"表", "table"} if role == "table-caption" else {"图", "figure"}
            add("caption_match" if f["caption_pattern"] in expected else "caption_absent",
                75 if f["caption_pattern"] in expected else -60, "题注编号类型与候选匹配程度")
            if short:
                add("caption_short", 15, "独立短题注")
            if f["text_length"] > 80 or f["body_sentence"]:
                add("caption_sentence", -65, "长句或完整正文句不宜仅凭开头判为题注")
        elif role == "reference-heading":
            add("reference_boundary", 100 if f["reference_boundary"] else -80,
                "匹配独立参考文献边界" if f["reference_boundary"] else "未匹配参考文献边界")
        elif role == "reference-entry":
            if f["text_length"]:
                add("reference_text", 20, "非空参考条目候选")
            if f["reference_entry_pattern"]:
                add("reference_entry_pattern", 35, "具有方括号文献序号")
            if f["body_sentence"]:
                add("reference_sentence", 10, "文字具备条目内容")
            if f["reference_boundary"]:
                add("reference_is_boundary", -70, "边界标题不是文献条目")
        elif role == "unknown":
            if f["author_name_list_pattern"]:
                add("unconfirmed_author_list", 150, "姓名列表缺少文前上下文时保留，不接受脏 Heading 样式")
            if not f["text_length"]:
                add("empty_paragraph", 150, "空段落不判定内容角色")
            if f["list"]:
                add("unsupported_list", 150, "自动列表继续保留")
            if f["custom_style"] and not f["body_sentence"]:
                add("custom_style_weak_content", 65, "自定义样式且缺少完整正文内容证据")
            if f["has_complex_object"] or f["has_manual_break"]:
                add("complex_object", 150, "域、图形、嵌入对象、数学对象或手工换行需保留结构")
            if not any((f["native_heading_level"], f["numbering_family"], metadata,
                        f["body_sentence"], f["caption_pattern"], f["reference_boundary"])):
                add("weak_content", 15, "缺少明确语义线索")
        if role != "unknown":
            if not f["text_length"]:
                add("no_text", -150, "空段落没有可判定文字")
            if role != "body-table" and f["table_context"] is not None and not role.startswith("heading-") and role != "body-paragraph":
                add("non_table_role_in_table", -120, "表格上下文与文档级角色冲突")
            if f["list"] and role != "body-paragraph" and not role.startswith("heading-"):
                add("role_in_list", -100, "自动列表内容保留")
            if f["has_complex_object"] or f["has_manual_break"]:
                add("role_complex_object", -200 if f["has_embedded_object"] or f["has_math"] else -100,
                    "复杂对象降低可安全判定程度；嵌入公式不得由原生标题及编号证据升格")
    return candidates


def decide(candidates: list[RoleCandidate], config: ScoringConfig) -> ClassificationDecision:
    """Resolve competition; confidence is a bounded heuristic, not a probability."""

    ranked = sorted(candidates, key=lambda c: (-c.resolved_score, c.role))
    top, second = ranked[:2]
    score = top.resolved_score
    margin = score - second.resolved_score
    hierarchy_conflict = any(e.feature == "hierarchy_jump" for e in top.evidence)
    high = score >= config.high_score and margin >= config.high_margin and not hierarchy_conflict
    medium = score >= config.medium_score
    band: Literal["high", "medium", "low"] = "high" if high else "medium" if medium else "low"
    role = top.role if medium and margin >= config.ambiguous_margin else "unknown"
    action: Action = "mapped" if high and role != "unknown" and not hierarchy_conflict else (
        "uncertain" if medium and role != "unknown" else "preserved"
    )
    strength = min(1.0, max(0.0, score) / max(config.high_score, 1))
    separation = min(1.0, max(0.0, margin) / config.high_margin)
    confidence = strength * (0.65 + 0.35 * separation)
    if action != "mapped":
        confidence = min(confidence, 0.89 if medium else 0.69)
    reasons = [
        f"第一候选 {top.role}={score:g}；第二候选 {second.role}={second.resolved_score:g}；分差={margin:g}",
        f"阈值：高分 {config.high_score:g} 且分差 {config.high_margin:g}；中分 {config.medium_score:g}；歧义分差 {config.ambiguous_margin:g}",
        f"证据强度={band}，最终角色={role}，动作={action}；confidence 为启发式强度而非概率",
    ]
    if hierarchy_conflict:
        reasons.append("出现异常标题层级跳跃，禁止高置信映射")
    if role == "unknown":
        reasons.append("未知类型、证据不足或候选接近，保留原样")
    return ClassificationDecision(
        role=role, confidence=round(confidence, 4), action=action, reasons=reasons,
        score=score, margin=margin, top_role=top.role, runner_up_role=second.role,
        runner_up_score=second.resolved_score, confidence_band=band,
    )
