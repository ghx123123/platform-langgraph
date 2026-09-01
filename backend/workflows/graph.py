import asyncio
import logging
import operator
import re
from typing import Annotated, Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.workflows.llm import ModelClient
from backend.workflows.models import TeachingMessage, WorkflowTemplate


logger = logging.getLogger("multi_agent_platform.workflows.graph")

EmitEvent = Callable[[str, str | None, str, dict[str, Any]], Awaitable[None]]


class WorkflowState(TypedDict, total=False):
    run_id: str
    title: str
    document_name: str
    document_text: str
    context: str
    template_id: str
    knowledge_points: list[dict[str, Any]]
    document_sections: list[dict[str, Any]]
    content_analysis: dict[str, Any]
    teaching_framework: dict[str, Any]
    messages: Annotated[list[dict[str, Any]], operator.add]
    supervisor_review: dict[str, Any]
    current_iteration: int
    max_iterations: int
    interventions: dict[str, Any]
    scope: dict[str, Any]
    final_output: str
    status: str


def _message(
    agent_id: str,
    agent_name: str,
    agent_type: str,
    phase: str,
    iteration: int,
    content: str,
    level: str | None = None,
) -> dict[str, Any]:
    return TeachingMessage(
        agent_id=agent_id,
        agent_name=agent_name,
        agent_type=agent_type,
        phase=phase,
        iteration=iteration,
        content=content.strip(),
        level=level,
    ).model_dump(mode="json")


def _fallback_points(text: str) -> list[dict[str, Any]]:
    """未随请求提交知识点时，复用文档解析的抽取逻辑，避免两套算法产生差异。"""
    from backend.documents.service import extract_knowledge_points

    return [point.model_dump() for point in extract_knowledge_points(text)]


def _scoped_point_titles(state: WorkflowState) -> list[str]:
    """只返回教师在启动前确认的范围；旧会话未保存范围时保持全量兼容。"""
    titles = _point_titles(state)
    selected = {str(item).strip() for item in state.get("scope", {}).get("selected_point_titles", []) if str(item).strip()}
    return [title for title in titles if title in selected] or titles


def _scope_brief(state: WorkflowState) -> str:
    scope = state.get("scope", {})
    depth_names = {"overview": "概览梳理", "standard": "标准掌握", "deep": "深入打磨"}
    titles = _scoped_point_titles(state)
    return (
        f"指定知识点：{'；'.join(titles) or state.get('title', '')}\n"
        f"课时：{scope.get('estimated_minutes', 45)} 分钟\n"
        f"讲解深度：{depth_names.get(scope.get('depth'), '标准掌握')}"
    )


def _round_focus(state: WorkflowState, iteration: int) -> str:
    """每轮都围绕同一教师确认范围进行改进，不再轮换到未指定的新知识点。"""
    titles = _scoped_point_titles(state)
    # 跳过与课程名同级的章级标题（如“内置对象、运算符、表达式、关键字”），
    # 避免把整章内容当成一个“本轮重点”而失去聚焦；无其他点时回退章标题。
    course = state.get("title", "")
    core = re.sub(r"^第[一二三四五六七八九十0-9]+章[：:\s]*", "", course).strip(" ：:")
    pool = [t for t in titles if t != core and core not in t] or titles
    return "；".join(pool) if pool else course


def _point_titles(state: WorkflowState) -> list[str]:
    return [item.get("title", "") for item in state.get("knowledge_points", []) if item.get("title")]


def _contrast_point(state: WorkflowState, iteration: int) -> str:
    """与本轮重点相对照的另一个知识点，用于学生辨析类提问。"""
    titles = _scoped_point_titles(state)
    course = state.get("title", "")
    core = re.sub(r"^第[一二三四五六七八九十0-9]+章[：:\s]*", "", course).strip(" ：:")
    pool = [t for t in titles if t != core and core not in t] or titles
    focus = _round_focus(state, iteration)
    others = [t for t in pool if t != focus] or pool
    if not others:
        return "它的适用条件"
    return others[iteration % len(others)]


def _fallback_exercises(titles: list[str]) -> list[dict[str, str]]:
    """未随模型返回练习时，按知识点生成三层课堂练习（基础/进阶/拓展）。"""
    focus = titles[0] if titles else "本课核心概念"
    second = titles[1] if len(titles) > 1 else focus
    return [
        {
            "level": "low",
            "question": f"用自己的话说一说“{focus}”的含义，并举一个例子。",
            "answer": f"答案要点：先给出{focus}的定义，再结合教材示例说明其特点与适用条件。",
        },
        {
            "level": "medium",
            "question": f"运用“{focus}”与“{second}”完成一道典型练习，并写出关键步骤。",
            "answer": f"答案要点：先识别题目涉及的知识点（{focus}、{second}），再按步骤求解并检查条件是否满足。",
        },
        {
            "level": "high",
            "question": f"如果改变{focus}的一个前提条件，结论还会成立吗？请举例说明。",
            "answer": f"答案要点：指出被改变的条件，分析其对结论的影响，并给出成立或不成立的反例。",
        },
    ]


def _document_sections(state: WorkflowState) -> list[dict[str, Any]]:
    sections = state.get("document_sections") or []
    if sections:
        return sections
    from backend.documents.service import extract_document_sections

    return [section.model_dump() for section in extract_document_sections(state.get("document_text", ""))]


def _section_content(document_text: str, section: dict[str, Any]) -> str:
    start = max(0, int(section.get("start_offset", 0)))
    end = min(len(document_text), int(section.get("end_offset", len(document_text))))
    return document_text[start:end].strip()


def _term_matches(term: str, content: str) -> bool:
    normalized = re.sub(r"\s+", "", term)
    compact = re.sub(r"\s+", "", content)
    if normalized and normalized in compact:
        return True
    pieces = [piece for piece in re.split(r"[、，；：/与和及()（）\s]+", term) if len(piece) >= 2]
    return bool(pieces) and sum(piece in content for piece in pieces) >= min(2, len(pieces))


def _analysis_material(state: WorkflowState, sections: list[dict[str, Any]]) -> str:
    """覆盖全部目录并均匀抽样，同时为教师选定范围保留更多原文。"""
    document_text = state.get("document_text", "")
    selected = _scoped_point_titles(state)
    directory = "\n".join(
        f"- {section.get('id')}｜{'  ' * max(0, int(section.get('level', 1)) - 1)}{section.get('title')}"
        for section in sections
    )
    samples = []
    focused = []
    for section in sections:
        content = _section_content(document_text, section)
        compact = re.sub(r"\s+", " ", content)
        samples.append(f"[{section.get('id')}] {section.get('title')}：{compact[:180]}")
        if any(_term_matches(title, f"{section.get('title', '')}\n{content}") for title in selected):
            focused.append(f"## {section.get('title')}\n{content[:2400]}")
    return (
        f"全文结构目录（共 {len(sections)} 个分区，全部纳入扫描）：\n{directory}\n\n"
        f"各分区内容抽样：\n{'\n'.join(samples)}\n\n"
        f"教师指定范围相关原文：\n{'\n\n'.join(focused) if focused else document_text[:12000]}"
    )[:36000]


def _section_analysis(
    state: WorkflowState,
    sections: list[dict[str, Any]],
    analysis: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    document_text = state.get("document_text", "")
    selected = _scoped_point_titles(state)
    related_terms = list(dict.fromkeys([
        *analysis.get("key_points", []),
        *analysis.get("difficult_points", []),
        *analysis.get("prerequisites", []),
    ]))
    insights: list[dict[str, Any]] = []
    focused_count = 0
    support_count = 0
    for section in sections:
        content = _section_content(document_text, section)
        searchable = f"{section.get('title', '')}\n{content}"
        matched = [title for title in selected if _term_matches(title, searchable)]
        supporting = [term for term in related_terms if term not in matched and _term_matches(str(term), searchable)]
        if matched:
            relevance = "core"
            focused_count += 1
        elif supporting:
            relevance = "support"
            support_count += 1
        else:
            relevance = "context"
        insights.append({
            "section_id": section.get("id"),
            "title": section.get("title"),
            "relevance": relevance,
            "matched_points": matched[:6],
            "related_concepts": supporting[:4],
            "evidence": section.get("preview") or re.sub(r"\s+", " ", content)[:180],
            "status": "analyzed",
        })
    total = len(sections)
    coverage = {
        "total_sections": total,
        "analyzed_sections": total,
        "coverage_percent": 100 if total else 0,
        "focused_sections": focused_count,
        "support_sections": support_count,
        "context_sections": max(0, total - focused_count - support_count),
        "method": "全目录扫描、逐区抽样、指定范围原文深读",
    }
    return insights, coverage


def build_workflow_graph(
    template: WorkflowTemplate,
    model: ModelClient,
    emit: EmitEvent,
    checkpointer: Any,
):
    async def content_analysis(state: WorkflowState) -> dict[str, Any]:
        await emit("node.started", "content_analysis", "教师正在剖析课程材料的知识结构与重难点", {"phase": "design"})
        points = state.get("knowledge_points") or _fallback_points(state["document_text"])
        sections = _document_sections(state)
        titles = _scoped_point_titles({**state, "knowledge_points": points})
        prompt = (
            "你是学科教师和课程内容分析专家。仅返回 JSON 对象，字段为 summary、key_points、"
            "difficult_points、prerequisites、learner_misconceptions；后四项均为字符串数组。"
        )
        user_material = (
            f"课程：{state['title']}\n{_scope_brief({**state, 'knowledge_points': points})}\n只设计指定知识点，但必须先检查全文结构和各分区证据。\n材料：{_analysis_material({**state, 'knowledge_points': points}, sections)}\n补充说明：{state.get('context') or '无'}"
        )
        try:
            provider = getattr(model, "provider", "")
            if provider == "dsh" and not model.is_mock:
                # dsh 完整 agent 能力：多轮记忆 + 自主迭代。同一 session 内迭代 2 轮，
                # 每轮基于上一轮产出修订(补全遗漏/修正疏漏/规范化 JSON), 越迭代越收敛。
                raw = await model.agent_iterate(
                    prompt, user_material, iterations=2,
                    round_focus="请把上一版修正规范化：重排 key_points 使其成体系(概念→语法→应用)、补全遗漏的难点与误区、修正疏漏；最终版必须是一个完整合法的 JSON 对象，且不要用代码块包裹。",
                )
                # 优先纯提取(不二次调用); 若末轮 JSON 不规整导致提取失败, 退一步用 generate_json 重试,
                # 避免"提取失败→清零兜底"导致下游空 analysis 或 run 失败。
                try:
                    analysis = model._extract_json_text(raw.get("final_response", ""))
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "content_analysis 迭代末轮 JSON 提取失败(%s)，回退 generate_json 重试。末轮输出前300字: %s",
                        exc, str(raw.get("final_response", ""))[:300],
                    )
                    analysis = await model.generate_json(prompt, user_material)
            else:
                analysis = await model.generate_json(prompt, user_material)
        except (ValueError, TypeError) as exc:
            logger.warning("content_analysis 未能解析模型 JSON，使用兜底内容: %s", exc)
            await emit("node.degraded", "content_analysis", "模型未返回可解析的结构化内容，本节使用通用模板", {"phase": "design", "reason": str(exc)})
            analysis = {}
        analysis = {
            "summary": analysis.get("summary") or f"本课程围绕“{state['title']}”组织内容，需要建立概念理解、方法应用与迁移反思的递进关系。",
            "key_points": analysis.get("key_points") or titles[:3] or ["核心概念与基本方法"],
            "difficult_points": analysis.get("difficult_points") or titles[1:4] or ["知识迁移与综合应用"],
            "prerequisites": analysis.get("prerequisites") or ["相关基础概念", "基本问题分析能力"],
            "learner_misconceptions": analysis.get("learner_misconceptions") or ["只记结论而忽略适用条件", "概念之间的边界容易混淆"],
        }
        section_insights, coverage = _section_analysis(
            {**state, "knowledge_points": points}, sections, analysis
        )
        analysis["section_insights"] = section_insights
        analysis["document_coverage"] = coverage
        message = _message(
            "teacher", "课程教师", "teacher", "design", 0,
            "课程内容分析完成。\n\n重点：" + "；".join(analysis["key_points"]) +
            "\n难点：" + "；".join(analysis["difficult_points"]) +
            "\n常见误区：" + "；".join(analysis["learner_misconceptions"]),
        )
        await emit("node.completed", "content_analysis", "课程重难点分析完成", {"phase": "design", "analysis": analysis, "knowledge_points": points, "document_sections": sections, "messages": [message]})
        return {"content_analysis": analysis, "knowledge_points": points, "document_sections": sections, "messages": [message], "status": "running"}

    async def teaching_design(state: WorkflowState) -> dict[str, Any]:
        refining = bool(state.get("teaching_framework")) and state.get("current_iteration", 0) > 0
        target_iteration = state.get("current_iteration", 0) + 1
        action = "根据上一轮督导意见打磨同一教学设计" if refining else "正在设计教学目标与课堂环节"
        await emit("node.started", "teaching_design", action, {"phase": "design", "iteration": target_iteration, "refinement": refining})
        analysis = state["content_analysis"]
        previous_framework = state.get("teaching_framework", {})
        review = state.get("supervisor_review", {})
        design_task = (
            "在不改变指定知识点、课时和讲解深度的前提下，重做教学设计。必须吸收上一轮督导建议，"
            "明确本轮相较上一版调整了什么；不要按章节推进到新的知识点。"
            if refining else "根据内容分析设计可实施课堂。"
        )
        try:
            framework = await model.generate_json(
                "你是教学设计教师。仅返回 JSON：learning_objectives字符串数组、stages对象数组（name、purpose、activity、minutes）、strategies字符串数组、assessment字符串数组、ideological_elements对象数组（dimension、content、integration_method）、exercises对象数组（level：low/medium/high、question、answer）、iteration_prompt字符串。课程思政必须与已选知识点或工程案例自然对应，不得加入与材料无关的口号。所有 stages 的 minutes 总和应接近指定课时。iteration_prompt 是可直接复用的下一轮教学设计提示词，须包含固定范围、要改进的具体动作和禁止扩展范围的约束。",
                f"课程：{state['title']}\n{_scope_brief(state)}\n任务：{design_task}\n内容分析：{analysis}\n上一版教学设计：{previous_framework or '无'}\n上一轮督导：{review or '首轮，无'}\n教师补充要求：{state.get('context') or '无'}",
            )
        except (ValueError, TypeError) as exc:
            logger.warning("teaching_design 未能解析模型 JSON，使用兜底内容: %s", exc)
            await emit("node.degraded", "teaching_design", "模型未返回可解析的教学框架，本节使用通用模板", {"phase": "design", "reason": str(exc)})
            framework = {}
        framework = {
            "learning_objectives": framework.get("learning_objectives") or previous_framework.get("learning_objectives") or ["准确解释核心概念", "运用方法分析典型问题", "识别常见误区并说明适用条件"],
            "stages": framework.get("stages") or previous_framework.get("stages") or [
                {"name": "情境导入", "purpose": "激活先备知识", "activity": "问题情境与快速诊断", "minutes": 8},
                {"name": "重点讲授", "purpose": "建立知识结构", "activity": "概念讲解、例证与对比", "minutes": 22},
                {"name": "分层探究", "purpose": "突破认知难点", "activity": "学生提问与教师追问", "minutes": 12},
                {"name": "评价总结", "purpose": "检验目标达成", "activity": "形成性评价与迁移任务", "minutes": 8},
            ],
            "strategies": framework.get("strategies") or previous_framework.get("strategies") or ["问题驱动", "对比辨析", "即时反馈"],
            "assessment": framework.get("assessment") or previous_framework.get("assessment") or ["观察概念表述的准确性", "检查典型任务完成质量"],
            "ideological_elements": framework.get("ideological_elements") or previous_framework.get("ideological_elements") or [],
            "exercises": framework.get("exercises") or previous_framework.get("exercises") or _fallback_exercises(_scoped_point_titles(state)),
            "iteration_prompt": framework.get("iteration_prompt") or review.get("iteration_prompt") or f"围绕 {_round_focus(state, target_iteration)}，在 {state.get('scope', {}).get('estimated_minutes', 45)} 分钟内，根据督导建议优化教学设计；不得扩展到未指定知识点。",
        }
        stage_text = "\n".join(f"{i + 1}. {stage['name']}：{stage['activity']}（{stage['minutes']} 分钟）" for i, stage in enumerate(framework["stages"]))
        design_label = f"第 {target_iteration} 轮教学设计已按督导建议打磨。" if refining else "教学方案已形成。"
        message = _message("teacher", "课程教师", "teacher", "design", target_iteration if refining else 0, f"{design_label}\n\n教学范围：{_round_focus(state, target_iteration)}\n\n学习目标：{'；'.join(framework['learning_objectives'])}\n\n教学环节：\n{stage_text}\n\n可复用优化提示词：\n{framework['iteration_prompt']}")
        await emit("node.completed", "teaching_design", "教学设计已完成打磨" if refining else "教学目标、活动与评价框架设计完成", {"phase": "design", "iteration": target_iteration, "framework": framework, "messages": [message], "refinement": refining})
        extra: list[dict[str, Any]] = []

        if state.get("interventions", {}).get("after_design") and not refining:
            decision = interrupt({
                "kind": "design_review",
                "iteration": 0,
                "prompt": "教学设计已就绪。你可以直接开始授课，或提出修改意见由教师重新设计。",
                "context": {"learning_objectives": framework["learning_objectives"], "stages": framework["stages"]},
            })
            note = str(decision.get("content", "")).strip()
            if decision.get("action") == "revise" and note:
                framework, message, extra = await _revise_design(state, framework, note)

        return {"teaching_framework": framework, "messages": [message, *extra]}

    async def _revise_design(
        state: WorkflowState, framework: dict[str, Any], note: str
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        """按用户意见重做教学设计。用户意见入档，便于回溯这一轮为何调整。"""
        await emit("node.started", "teaching_design", "教师正在按你的意见调整教学设计", {"phase": "design", "revision": True})
        user_message = _message("user", "教研员（你）", "teacher", "design", 0, f"对教学设计的修改意见：\n\n{note}")
        try:
            revised = await model.generate_json(
                "你是教学设计教师。根据教研员意见修订教学方案，仅返回 JSON：learning_objectives字符串数组、"
                "stages对象数组（name、purpose、activity、minutes）、strategies字符串数组、assessment字符串数组。",
                f"课程：{state['title']}\n原方案：{framework}\n教研员意见：{note}\n内容分析：{state['content_analysis']}",
            )
        except (ValueError, TypeError) as exc:
            logger.warning("teaching_design 修订未能解析模型 JSON，保留原方案: %s", exc)
            await emit("node.degraded", "teaching_design", "模型未返回可解析的修订方案，保留原方案", {"phase": "design", "reason": str(exc)})
            return framework, user_message, []

        merged = {key: revised.get(key) or framework[key] for key in framework}
        stage_text = "\n".join(f"{i + 1}. {s['name']}：{s['activity']}（{s['minutes']} 分钟）" for i, s in enumerate(merged["stages"]))
        revised_message = _message(
            "teacher", "课程教师", "teacher", "design", 0,
            f"已根据你的意见调整教学方案。\n\n学习目标：{'；'.join(merged['learning_objectives'])}\n\n教学环节：\n{stage_text}",
        )
        await emit("node.completed", "teaching_design", "教学方案已按你的意见修订", {"phase": "design", "framework": merged, "messages": [user_message, revised_message]})
        return merged, user_message, [revised_message]

    async def teacher_teaches(state: WorkflowState) -> dict[str, Any]:
        iteration = state.get("current_iteration", 0) + 1
        await emit("node.started", "teach_knowledge", f"教师开始第 {iteration} 轮知识讲授", {"phase": "teach_knowledge", "iteration": iteration})
        previous = state.get("supervisor_review", {})
        focus = _round_focus(state, iteration)
        async def _stream_token(text: str) -> None:
            await emit("node.token", "teach_knowledge", "正在生成讲授内容", {"phase": "teach_knowledge", "iteration": iteration, "text": text})

        content = await model.generate(
            "你是课程教师。进行自然、准确、面向课堂的口头讲授。不要使用 <details>、<summary> 等网页标签，不要输出 Markdown 表格（需对比时用自然语言分点）。讲授需包含：①生活化或代码化的导入；②核心概念解释，含 1-2 个可运行的 Python 代码示例；③2 个课堂小练习——先给学生停顿口答的时间，再公布答案与解析；④一个检查理解的追问。若有督导建议要在本轮体现。",
            f"课程：{state['title']}\n{_scope_brief(state)}\n第 {iteration} 轮固定教学范围：{focus}\n本轮目标是打磨同一范围的教学设计，不得顺延到新的章节或未指定知识点。\n教学框架：{state['teaching_framework']}\n上轮督导：{previous or '首轮，无'}\n材料依据：{state['document_text'][:12000]}",
            on_chunk=_stream_token,
        )
        message = _message("teacher", "课程教师", "teacher", "teach_knowledge", iteration, content)
        await emit("node.completed", "teach_knowledge", f"第 {iteration} 轮知识讲授完成", {"phase": "teach_knowledge", "iteration": iteration, "messages": [message], "output": content})
        return {"current_iteration": iteration, "messages": [message]}

    async def students_question(state: WorkflowState) -> dict[str, Any]:
        iteration = state["current_iteration"]
        await emit("node.started", "student_question", f"三类学生正在针对第 {iteration} 轮内容提问", {"phase": "student_question", "iteration": iteration})
        lecture = next((m["content"] for m in reversed(state["messages"]) if m["phase"] == "teach_knowledge" and m["iteration"] == iteration), "")
        round_focus = _round_focus(state, iteration)
        profiles = [
            ("student_high", "拓展型学生", "high", "追问知识边界、迁移应用或反例"),
            ("student_medium", "进阶型学生", "medium", "追问推理步骤、概念联系或典型应用"),
            ("student_low", "基础型学生", "low", "询问术语含义、基本步骤或易混点"),
        ]
        messages = []
        # 三类学生互不依赖，并发提问；gather 保序，输出仍为 拓展→进阶→基础
        questions = await asyncio.gather(*(
            model.generate(
                f"你是{name}。{focus}。只提出一个具体、自然的问题，不要回答，不要使用标题。",
                f"课程：{state['title']}\n本轮重点：{round_focus}\n对照知识点：{_contrast_point(state, iteration)}\n教师刚才讲授：{lecture[:6000]}",
            )
            for _, name, _, focus in profiles
        ))
        for (agent_id, name, level, _), question in zip(profiles, questions):
            messages.append(_message(agent_id, name, "student", "student_question", iteration, question, level))
        await emit("node.completed", "student_question", f"第 {iteration} 轮分层学生提问完成", {"phase": "student_question", "iteration": iteration, "messages": messages})
        return {"messages": messages}

    async def teacher_answers(state: WorkflowState) -> dict[str, Any]:
        iteration = state["current_iteration"]
        questions = [m for m in state["messages"] if m["phase"] == "student_question" and m["iteration"] == iteration]
        question_text = "\n".join(f"{m['agent_name']}：{m['content']}" for m in questions)

        action, note = "agent", ""
        if state.get("interventions", {}).get("after_question"):
            decision = interrupt({
                "kind": "answer_choice",
                "iteration": iteration,
                "prompt": "三位学生已提出问题。你可以自己回答、给出要点由教师扩写，或直接交给教师智能体。",
                "context": {"questions": [{"agent_name": m["agent_name"], "level": m.get("level"), "content": m["content"]} for m in questions]},
            })
            action = str(decision.get("action") or "agent")
            note = str(decision.get("content", "")).strip()

        # 用户全文作答时不调用模型，直接署名为用户
        if action == "user" and note:
            await emit("node.started", "teacher_answer", f"你正在回应第 {iteration} 轮学生问题", {"phase": "teacher_answer", "iteration": iteration})
            message = _message("user", "教研员（你）", "teacher", "teacher_answer", iteration, note)
            await emit("node.completed", "teacher_answer", f"第 {iteration} 轮由你完成答疑", {"phase": "teacher_answer", "iteration": iteration, "messages": [message], "output": note})
            return {"messages": [message]}

        if action == "outline" and note:
            await emit("node.started", "teacher_answer", f"教师正在按你的要点扩写第 {iteration} 轮答疑", {"phase": "teacher_answer", "iteration": iteration})
            system = ("你是课程教师。严格依据教研员给出的要点展开答疑，不得偏离其判断与结论；"
                      "逐一回应不同层次学生的问题，先直接回答，再解释依据，必要时用例子澄清误区，最后做简短归纳。")
            user = (f"课程：{state['title']}\n本轮重点：{_round_focus(state, iteration)}\n教研员要点：{note}\n"
                    f"学生问题：\n{question_text}\n材料依据：{state['document_text'][:10000]}")
        else:
            await emit("node.started", "teacher_answer", f"教师正在回应第 {iteration} 轮学生问题", {"phase": "teacher_answer", "iteration": iteration})
            system = "你是课程教师。逐一回应不同层次学生的问题，先直接回答，再解释依据，必要时用例子澄清误区，最后做简短归纳。"
            user = (f"课程：{state['title']}\n候选知识点：{'；'.join(_point_titles(state))}\n本轮重点：{_round_focus(state, iteration)}\n对照知识点：{_contrast_point(state, iteration)}\n"
                    f"学生问题：\n{question_text}\n材料依据：{state['document_text'][:10000]}")

        async def _answer_stream_token(text: str) -> None:
            await emit("node.token", "teacher_answer", "正在生成答疑内容", {"phase": "teacher_answer", "iteration": iteration, "text": text})

        answer = await model.generate(system, user, on_chunk=_answer_stream_token)
        extra = [_message("user", "教研员（你）", "teacher", "teacher_answer", iteration, f"答疑要点：\n\n{note}")] if action == "outline" and note else []
        message = _message("teacher", "课程教师", "teacher", "teacher_answer", iteration, answer)
        await emit("node.completed", "teacher_answer", f"第 {iteration} 轮教师答疑完成", {"phase": "teacher_answer", "iteration": iteration, "messages": [*extra, message], "output": answer})
        return {"messages": [*extra, message]}

    async def supervisor_comment(state: WorkflowState) -> dict[str, Any]:
        iteration = state["current_iteration"]
        await emit("node.started", "supervisor_comment", f"教学督导正在评价第 {iteration} 轮课堂", {"phase": "supervisor_comment", "iteration": iteration})
        round_messages = [m for m in state["messages"] if m["iteration"] == iteration]
        if model.is_mock:
            score = min(92, 78 + (iteration - 1) * 8)
            review = {
                "score": score,
                "dimensions": {"教学设计": score + 2, "讲授方式": score, "回答质量": score - 1},
                "strengths": ["教学主线清楚", "能够回应不同层次学生问题"],
                "weaknesses": ["部分概念边界仍需明确", "学生产出要求还不够具体"],
                "suggestions": ["进一步标注知识适用条件", "增加学生可观察的学习产出"],
                "next_focus": "下一轮结合学生误区强化概念边界与迁移练习",
                "iteration_prompt": f"围绕 {_round_focus(state, iteration)} 保持教学范围不变；根据本轮督导意见，强化概念边界、适用条件与迁移练习；在既定课时内重组教学环节，不扩展到未指定知识点。",
            }
        else:
            try:
                review_evidence = "\n\n".join(
                    f"[{message.get('phase', '')}/{message.get('agent_name', '')}]\n{str(message.get('content', ''))[:3000]}"
                    for message in round_messages
                )[:14000]
                review = await model.generate_json(
                    "你是高校教学督导。仅返回 JSON：score(0-100)、dimensions对象（教学设计、讲授方式、回答质量）、strengths字符串数组（优点）、weaknesses字符串数组（不足）、suggestions字符串数组（建议）、next_focus字符串、iteration_prompt字符串。每类最多输出3条，必须具体、简洁、可核对，禁止大段复述课堂记录。iteration_prompt 必须是教师可复制复用的下一轮教学设计提示词，包含：固定知识范围、具体改进动作、课时约束、不得扩展范围。",
                    f"课程：{state['title']}\n{_scope_brief(state)}\n本轮课堂证据：\n{review_evidence}",
                )
                required = ("score", "dimensions", "strengths", "weaknesses", "suggestions", "next_focus", "iteration_prompt")
                missing = [key for key in required if not review.get(key)]
                if missing:
                    raise ValueError(f"Supervisor JSON missing required fields: {', '.join(missing)}")
            except (ValueError, TypeError) as exc:
                logger.warning("supervisor_comment 未能解析模型 JSON，使用兜底评价: %s", exc)
                await emit("node.degraded", "supervisor_comment", "模型未返回可解析的督导评分，本轮使用兜底评价", {"phase": "supervisor_comment", "iteration": iteration, "reason": str(exc)})
                review = {}
            score = max(0, min(100, int(review.get("score", 75))))
            review = {
                "score": score,
                "dimensions": review.get("dimensions") or {"教学设计": score, "讲授方式": score, "回答质量": score},
                "strengths": review.get("strengths") or ["完成了讲授、提问与答疑闭环"],
                "weaknesses": review.get("weaknesses") or ["部分教学环节仍可进一步收束"],
                "suggestions": review.get("suggestions") or ["下一轮根据学生问题调整讲授重点"],
                "next_focus": review.get("next_focus") or "围绕学生暴露出的误区开展针对性教学",
                "iteration_prompt": review.get("iteration_prompt") or f"围绕 {_round_focus(state, iteration)} 保持教学范围不变；根据督导建议优化教学环节与解释方式；在既定课时内完成，不扩展到未指定知识点。",
            }
        bullet_lines = lambda items: "\n".join(f"- {item}" for item in items[:3])
        comment = (
            f"本轮综合评价：{review['score']} 分。\n\n"
            f"优点：\n{bullet_lines(review['strengths'])}\n\n"
            f"不足：\n{bullet_lines(review['weaknesses'])}\n\n"
            f"建议：\n{bullet_lines(review['suggestions'])}\n"
            f"- 下一轮重点：{review['next_focus']}\n\n"
            f"可复用优化提示词：\n{review['iteration_prompt']}"
        )
        message = _message("supervisor", "教学督导", "supervisor", "supervisor_comment", iteration, comment)
        await emit("review.completed", "supervisor_comment", f"第 {iteration} 轮督导点评完成，综合 {review['score']} 分", {"phase": "supervisor_comment", "iteration": iteration, "review": review, "messages": [message]})
        await emit("phase.completed", "supervisor_comment", f"第 {iteration} 轮教学闭环完成", {"phase": "iteration_complete", "iteration": iteration})
        return {"supervisor_review": review, "messages": [message]}

    def route_iteration(state: WorkflowState) -> str:
        if state["current_iteration"] >= state["max_iterations"]:
            return "finalize"
        return "refine"

    async def finalize(state: WorkflowState) -> dict[str, Any]:
        await emit("node.started", "finalize", "正在汇总教学设计与课堂改进成果", {"phase": "iteration_complete"})
        objectives = state["teaching_framework"].get("learning_objectives", [])
        analysis = state["content_analysis"]
        review = state.get("supervisor_review", {})
        report = (
            f"# {state['title']}教学设计成果\n\n"
            f"## 教学范围\n{_scope_brief(state)}\n\n"
            f"## 课程内容剖析\n{analysis.get('summary', '')}\n\n"
            f"重点：{'；'.join(analysis.get('key_points', []))}\n\n"
            f"难点：{'；'.join(analysis.get('difficult_points', []))}\n\n"
            f"## 学习目标\n" + "\n".join(f"- {item}" for item in objectives) + "\n\n"
            f"## 教学实施\n共完成 {state['current_iteration']} 轮“教师讲授 - 学生提问 - 教师答疑 - 督导点评”闭环。\n\n"
            f"## 督导结论\n综合评分：{review.get('score', '--')} 分。\n"
            f"优点：{'；'.join(review.get('strengths', []))}\n\n"
            f"不足：{'；'.join(review.get('weaknesses', []))}\n\n"
            f"建议：{'；'.join(review.get('suggestions', []))}\n\n"
            f"## 可复用优化提示词\n{review.get('iteration_prompt') or state['teaching_framework'].get('iteration_prompt', '')}\n"
        )
        await emit("node.completed", "finalize", "教学设计全流程完成", {"phase": "iteration_complete", "output": report, "review": review})
        return {"final_output": report, "status": "completed"}

    def route_entry(state: WorkflowState) -> str:
        """追加轮次时已有分析与教学方案，直接从讲授开始，不重做前置节点。"""
        return "refine" if state.get("teaching_framework") else "analyze"

    graph = StateGraph(WorkflowState)
    graph.add_node("content_analysis", content_analysis)
    graph.add_node("teaching_design", teaching_design)
    graph.add_node("teach_knowledge", teacher_teaches)
    graph.add_node("student_question", students_question)
    graph.add_node("teacher_answer", teacher_answers)
    graph.add_node("supervisor_comment", supervisor_comment)
    graph.add_node("finalize", finalize)
    graph.add_conditional_edges(START, route_entry, {"analyze": "content_analysis", "refine": "teaching_design"})
    graph.add_edge("content_analysis", "teaching_design")
    graph.add_edge("teaching_design", "teach_knowledge")
    graph.add_edge("teach_knowledge", "student_question")
    graph.add_edge("student_question", "teacher_answer")
    graph.add_edge("teacher_answer", "supervisor_comment")
    graph.add_conditional_edges("supervisor_comment", route_iteration, {"refine": "teaching_design", "finalize": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
