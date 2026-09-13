"""Prompt construction for one-shot Lesson Blueprint preparation."""

from __future__ import annotations

import json
from typing import Any


def build_lesson_blueprint_prompt(
    context: dict[str, Any],
    *,
    repair: bool = False,
    invalid_output: str = "",
    validation_error: str = "",
) -> tuple[str, str]:
    system = (
        "你是课程设计与教学脚本专家。当前任务是备课，不是上课。"
        "请只输出一个结构化 JSON 对象，不要 Markdown，不要生成师生对话。"
    )
    schema = {
        "title": "课程标题",
        "learning_objectives": ["可观察的学习目标"],
        "knowledge_points": ["知识点 ID 或名称"],
        "estimated_minutes": context.get("estimated_minutes", 45),
        "slides": [{
            "title": "页面标题", "purpose": "本页目的", "learning_objectives": [],
            "knowledge_points": [], "estimated_minutes": 5,
            "ppt_content": {"title": "", "subtitle": "", "bullets": [], "examples": [], "code_blocks": [], "visual_instruction": ""},
            "speaker_notes": [{"block_type": "EXPLANATION", "content": "教师讲解内容", "estimated_seconds": 60, "knowledge_point_ids": []}],
            "interaction_anchors": [{"interaction_type": "CHECK_UNDERSTANDING", "objective": "", "planned_question": "", "target_student_level": "all", "after_block_id": "", "knowledge_point_ids": [], "priority": 1}],
            "expected_misconceptions": [{"knowledge_point_id": "", "description": "", "observable_signals": [], "recommended_correction": ""}],
        }],
    }
    target_slide_count = context.get("target_slide_count")
    page_instruction = (
        f"必须生成恰好 {target_slide_count} 页，不能少页或多页；"
        if target_slide_count else "请控制在 5-8 页；"
    )
    allocation_instruction = (
        "平台已提供 slide_allocation。请严格按每页计划覆盖对应知识点；"
        "页数少于知识点时合并相关知识点，页数多于知识点时使用应用/综合页，"
        "不要按‘一页一个知识点’机械拆分，也不要遗漏计划中的知识点。"
        if context.get("slide_allocation") else ""
    )
    user = (
        "请根据以下课程资料生成 LessonVersion V1。PPT 要简洁，Speaker Notes 要比 PPT 详细；"
        "Interaction Anchor 只是互动机会；Expected Misconception 必须关联知识点；"
        "所有内容必须符合课程时间预算。speaker_notes.block_type 只能使用 "
        "OPENING、EXPLANATION、EXAMPLE、DEMONSTRATION、TRANSITION、QUESTION_PREP、SUMMARY、FEEDBACK；"
        "interaction_anchors.target_student_level 只能使用 high、medium、low、all；"
        f"不要创造 intermediate、basic、beginner 或 CHECK 等新枚举值。{page_instruction}{allocation_instruction}每页 1-3 个讲稿 Block；"
        "只输出必要内容，确保 JSON 能完整闭合。\n\n"
        f"输出结构示例：{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"课程上下文：{json.dumps(context, ensure_ascii=False)}"
    )
    if repair:
        user = (
            "下面是一份未通过校验的 Lesson Blueprint JSON。不要重新构思课程，"
            "只修复 JSON 语法、枚举、ID 引用、知识点引用或时间预算，并输出完整 JSON；"
            "target_student_level 只能使用 high、medium、low、all；"
            "不要解释、不要 Markdown。\n"
            f"校验错误：{validation_error}\n\n"
            f"课程上下文：{json.dumps(context, ensure_ascii=False)}\n\n"
            f"待修复内容：\n{invalid_output}"
        )
    return system, user


def build_supervisor_observation_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """Build a constrained, evidence-first prompt for one completed slide."""
    system = (
        "你是被动旁听的教学督导，只分析已经完成的当前 PPT 页面。"
        "只输出 JSON，不得作为课堂角色发言或控制课堂流程。"
        "issue 必须给出基于事件的具体教学判断，recommendation 必须是可执行的页面或讲稿修改建议；"
        "禁止输出‘已记录证据’‘建议查看事件’等没有判断价值的套话。"
    )
    schema = {
        "category": "accuracy|objective|clarity|interaction|questioning|feedback|misconception|pacing|alignment|other",
        "severity": "info|minor|major|critical",
        "event_ids": ["只能引用所提供的真实 event_id"],
        "issue": "与当前页面和事件直接关联的具体判断",
        "evidence": "引用事件所显示的事实",
        "recommendation": "可直接落实到当前 PPT、讲稿或互动锚点的建议",
        "directive_compliance": [
            {"directive_id": "上下文 teacher_directives 里的 id", "followed": True, "evidence": "支持判断的事件事实"}
        ],
    }
    directive_rule = ""
    if context.get("teacher_directives"):
        directive_rule = (
            "context.teacher_directives 是教师在课堂上明确下达的指令，必须逐条判定"
            "「本轮是否被遵守」(followed)，并给出证据；未遵守的指令要额外用一条 "
            "category=alignment 的 observation 指出。"
        )
    user = directive_rule + "\n分析当前页面并只输出中文 JSON：\n" + json.dumps({"schema": schema, "context": context}, ensure_ascii=False)
    return system, user


def build_supervisor_report_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """Build a round-level evidence prompt; total score is computed in code."""
    system = (
        "You are a passive classroom supervisor producing a round review. Return JSON only. "
        "Score each supplied dimension from 0 to 100 and cite observation ids; do not output speech."
    )
    schema = {
        "dimension_scores": {
            "content_accuracy": 0, "objective_achievement": 0, "explanation_clarity": 0,
            "interaction_quality": 0, "questioning_quality": 0, "feedback_quality": 0,
            "misconception_handling": 0, "pacing": 0, "ppt_speech_alignment": 0,
        },
        "strengths": [], "critical_issues": [], "observation_ids": [], "revision_priorities": [],
    }
    user = "Review this completed round and output only JSON:\n" + json.dumps({"schema": schema, "context": context}, ensure_ascii=False)
    return system, user


def build_revision_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """Build a patch-only revision prompt. The model must not rewrite a lesson."""
    system = (
        "You are a lesson revision planner. Return only a JSON array of minimal RevisionPatch objects. "
        "Never regenerate an entire lesson; preserve all content not targeted by a patch. "
        "Each patch must cite supplied observation ids and include before/after values."
    )
    schema = [{
        "target_type": "slide|speaker_note|interaction_anchor|misconception|lesson",
        "slide_id": "existing slide id", "block_id": "optional existing block id",
        "field_path": "ppt_content.bullets or content, etc.",
        "before": "exact current value", "after": "minimal replacement",
        "reason": "evidence-based reason", "source_observation_ids": ["OBS-id"],
    }]
    user = "Plan minimal patches and output only JSON:\n" + json.dumps({"schema": schema, "context": context}, ensure_ascii=False)
    return system, user


def build_lesson_slide_review_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """Ask the preparation Teacher to revise one slide without touching peers."""
    system = (
        "你是同一门课程的 Teacher Agent，正在与教师用户逐页完善备课草稿。"
        "只修改指定 Slide，不得重写其他页面，不得生成课堂中尚未发生的师生对话。"
        "只输出 JSON，不输出解释或隐藏思维过程。"
    )
    schema = {
        "title": "页面标题",
        "purpose": "本页教学目的",
        "ppt_content": {
            "title": "PPT 标题", "subtitle": "副标题", "bullets": ["简洁要点"],
            "examples": ["可观察案例"], "code_blocks": [], "visual_instruction": "视觉呈现建议",
        },
        "speaker_notes": [{
            "block_id": "必须沿用当前页已有 block_id；新增 Block 才留空",
            "block_type": "explanation|question|example|feedback|summary|transition|other",
            "content": "逐页教师讲稿", "estimated_seconds": 30,
            "knowledge_point_ids": ["只能使用当前课程知识点"],
        }],
        "interaction_anchors": [{
            "interaction_id": "必须沿用已有 interaction_id；新增锚点才留空",
            "type": "question|check|discussion|practice|reflection|other",
            "objective": "互动目标", "planned_question": "计划问题",
            "target_student_level": "high|medium|low|all",
            "after_block_id": "当前页真实 block_id", "knowledge_point_ids": ["当前课程知识点"],
            "priority": 1,
        }],
        "expected_misconceptions": [{
            "misconception_id": "必须沿用已有 misconception_id；新增误区才留空",
            "knowledge_point_id": "当前课程知识点", "description": "可观察误区",
            "observable_signals": ["可观察信号"], "correction_strategy": "纠正策略",
        }],
        "summary": "面向用户的一句话修改说明",
    }
    return system, (
        "根据用户意见完善当前页。保留 slide_id、已有 block_id/interaction_id/misconception_id "
        "和未要求改变的事实，PPT 简洁、讲稿具体。必须实际修改至少一个可见教学字段，"
        "不能只修改 summary。\n"
        + json.dumps({"schema": schema, **context}, ensure_ascii=False)
    )


# The definitions below intentionally live at the end of this module so older
# prompt helpers remain import-compatible while the classroom_v2 supervisor
# contract is upgraded in one place.
DEFAULT_SUPERVISOR_PROFILE: dict[str, Any] = {
    "role_definition": "你是本课程的课后教学督导。你只旁听和分析，不参与课堂发言，也不改变课堂流程。",
    "system_prompt": "评价必须基于当前 PPT、Speaker Notes 和实际 ClassroomEvent，逐页给出可执行判断。",
    "evaluation_focus": [
        "ppt_alignment",
        "teaching_coverage",
        "student_response_analysis",
        "feedback_quality",
        "misconception_handling",
        "objective_evidence",
    ],
}


def _supervisor_instructions(context: dict[str, Any]) -> str:
    profile = context.get("supervisor_profile") or DEFAULT_SUPERVISOR_PROFILE
    focus = ", ".join(str(item) for item in profile.get("evaluation_focus", []))
    return (
        f"角色定义：{profile.get('role_definition', DEFAULT_SUPERVISOR_PROFILE['role_definition'])}\n"
        f"本会话系统提示词：{profile.get('system_prompt', DEFAULT_SUPERVISOR_PROFILE['system_prompt'])}\n"
        f"本次重点：{focus or '逐页证据、讲解覆盖、师生互动和反馈质量'}\n"
        "只评价已经结束的页面；不要替教师、学生或编排器发言。"
    )


def build_directive_patch_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """把教师的课堂纠正变成最小补丁。只改被指出的地方，不重写整页。"""
    system = (
        "你是课程教师，正在把教研员在课堂上的纠正意见落实到课件。"
        "只输出一个 JSON 数组，每个元素是一个最小 RevisionPatch；不要重写整页，"
        "不要改动未被指出的内容。before 必须与当前值完全一致，after 是最小替换。"
    )
    schema = [{
        "target_type": "slide|speaker_note",
        "slide_id": "必须来自上下文里的真实 slide_id",
        "block_id": "target_type=speaker_note 时必填，来自真实 block_id",
        "field_path": "如 ppt_content.bullets 或 content",
        "before": "当前值原样复制",
        "after": "最小替换后的值",
        "reason": "引用教师指令的哪一点",
    }]
    user = (
        "根据教研员的纠正意见，生成最小补丁数组。只输出 JSON：\n"
        + json.dumps({"schema": schema, "context": context}, ensure_ascii=False)
    )
    return system, user


def build_supervisor_observation_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """Force the supervisor to analyse content, delivery and response evidence."""
    system = (
        "You are a passive post-class supervisor. Return JSON only and never join the classroom.\n"
        + _supervisor_instructions(context)
        + "\nEvery claim must cite supplied event_ids and a concrete slide/block/anchor. "
        "Do not write generic phrases such as 'increase interaction' or 'evidence recorded'."
    )
    schema = {
        "category": "accuracy|objective|clarity|interaction|questioning|feedback|misconception|pacing|alignment|other",
        "severity": "info|minor|major|critical",
        "event_ids": ["only supplied event_id values"],
        "issue": "specific judgment tied to this slide",
        "evidence": "what the cited PPT/notes/events prove",
        "recommendation": "minimal actionable change to this slide, block, or interaction anchor",
        "directive_compliance": [
            {"directive_id": "an id from context.teacher_directives", "followed": True, "evidence": "event fact supporting the judgment"}
        ],
        "analysis": {
            "ppt_alignment": "Does the teacher cover the slide title, bullets, examples and visual intent?",
            "teaching_coverage": "Which learning objective and knowledge points were actually explained?",
            "student_response_analysis": "For each answer/question/silence: correct, partial, wrong, uncertain, or missing evidence.",
            "feedback_analysis": "Did the teacher identify correct and incorrect parts, follow up, correct, and summarize?",
            "misconception_analysis": "Which expected misconception was exposed or not checked, with evidence.",
            "objective_evidence": "What event sequence supports or contradicts objective achievement?",
        },
    }
    directive_rule = ""
    if context.get("teacher_directives"):
        directive_rule = (
            "context.teacher_directives 是教研员在课堂上明确下达的指令，必须逐条判定本轮是否被遵守"
            "(directive_compliance, followed true/false)并给出证据。\n"
        )
    user = (
        directive_rule
        + "Analyse this completed slide. A student answer without teacher feedback is a feedback gap. "
        "A complete question -> answer -> feedback/follow-up -> summary chain must be analysed for quality, "
        "not described as merely 'interactive'. If no student evidence exists, say exactly that. Output JSON only.\n"
        + json.dumps({"schema": schema, "context": context}, ensure_ascii=False)
    )
    return system, user


def build_supervisor_report_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """Build an evidence-based round review prompt; code computes the weighted score."""
    system = (
        "You are a passive classroom supervisor producing an evidence-based round review. Return JSON only. "
        "Score every supplied dimension from 0 to 100 and cite observation ids; do not output speech.\n"
        + _supervisor_instructions(context)
    )
    schema = {
        "dimension_scores": {
            "content_accuracy": 0, "objective_achievement": 0, "explanation_clarity": 0,
            "interaction_quality": 0, "questioning_quality": 0, "feedback_quality": 0,
            "misconception_handling": 0, "pacing": 0, "ppt_speech_alignment": 0,
        },
        "strengths": [], "critical_issues": [], "observation_ids": [], "revision_priorities": [],
    }
    user = (
        "Review every supplied slide observation and event. Scores must reflect evidence, not a default average. "
        "Critical issues must name the slide and observation. Revision priorities must be implementable. Output JSON only:\n"
        + json.dumps({"schema": schema, "context": context}, ensure_ascii=False)
    )
    return system, user
