"""Deterministic single-round classroom orchestration (Phase 4)."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from .actions import FeedbackEvaluation, StudentAction, StudentActionType, TeacherAction, TeacherActionType
import asyncio
from .agent_services import StudentAgentService, TeacherAgentService
from .models import ClassroomEvent, ClassroomEventType, ClassroomState, LessonVersion, SimulationRound, StudentCognitiveState, StudentPersona, TeacherDirective, utc_now
from .policies import InteractionPolicy, VirtualTimePolicy
from .repository import ClassroomRepository


_UNSET = object()


@dataclass
class _Runtime:
    lesson: LessonVersion
    round: SimulationRound
    state: ClassroomState
    personas: list[StudentPersona]
    block_index: int = 0
    anchor_index: int = 0
    pending_event_id: str | None = None
    resume_phase: str | None = None
    # 生效中的教师指令(约束继承): 每次 agent 调用前注入 prompt
    active_directives: list[TeacherDirective] = field(default_factory=list)
    # 教师是否要求「学生提问后暂停」(classroom_v2 里真正生效的介入点)
    pause_after_student_question: bool = False
    # 因为该设置而暂停的轮次(供 integration 区分普通暂停)
    paused_for_question: bool = False


class ClassroomOrchestrator:
    def __init__(self, repository: ClassroomRepository, teacher: TeacherAgentService, students: StudentAgentService, *, policy: InteractionPolicy | None = None, virtual_time: VirtualTimePolicy | None = None, personas: list[StudentPersona] | None = None, cognitive_states: dict[str, list[StudentCognitiveState]] | None = None, on_event: Callable[[ClassroomEvent], Awaitable[None]] | None = None, on_slide_completed: Callable[[LessonVersion, SimulationRound, Any], Awaitable[None]] | None = None, on_round_completed: Callable[[LessonVersion, SimulationRound], Awaitable[None]] | None = None, pause_after_student_question: bool = False) -> None:
        self.repository, self.teacher, self.students = repository, teacher, students
        self.policy, self.virtual_time = policy or InteractionPolicy(), virtual_time or VirtualTimePolicy()
        self.personas = personas or []
        self.cognitive_states = cognitive_states or {}
        self.on_event = on_event
        self.on_slide_completed = on_slide_completed
        self.on_round_completed = on_round_completed
        self.pause_after_student_question = pause_after_student_question
        self._runs: dict[str, _Runtime] = {}

    async def start_round(self, lesson: LessonVersion, round_item: SimulationRound, *, personas: list[StudentPersona] | None = None) -> ClassroomState:
        if lesson.run_id != round_item.run_id:
            raise ValueError("lesson and round must belong to the same run")
        state = ClassroomState(run_id=round_item.run_id, round_id=round_item.id, phase="round_initializing", status="active")
        runtime = _Runtime(lesson, round_item, state, personas or self.personas)
        self._runs[round_item.id] = runtime
        await self.repository.ensure_run(round_item.run_id)
        for persona in runtime.personas:
            if persona.run_id != round_item.run_id:
                raise ValueError("student persona and round must belong to the same run")
            await self.repository.save_student_persona(persona)
        await self.repository.create_simulation_round(round_item)
        await self._persist_event(runtime, ClassroomEventType.ROUND_STARTED, "Round started", actor_id="system", actor_role="system")
        await self._persist_state(runtime, phase="slide_enter")
        return runtime.state

    async def restore_round(self, lesson: LessonVersion, round_item: SimulationRound) -> ClassroomState:
        """Reconstruct an in-memory runtime from SQLite snapshot + event history."""
        if lesson.run_id != round_item.run_id:
            raise ValueError("lesson and round must belong to the same run")
        state = await self.repository.get_classroom_state(round_item.id)
        if state is None:
            state = ClassroomState(run_id=round_item.run_id, round_id=round_item.id, phase="round_initializing", status="active")
        events = await self.repository.list_classroom_events(round_item.run_id, round_item.id)
        block_index = 0
        anchor_index = 0
        if state.current_block_id:
            for slide in lesson.slides:
                for index, block in enumerate(slide.speaker_notes):
                    if block.block_id == state.current_block_id:
                        block_index = index
                        break
        current_slide = (
            lesson.slides[state.current_slide_index]
            if state.current_slide_index < len(lesson.slides)
            else None
        )
        if current_slide is not None:
            executed_blocks = {
                str(event.metadata.get("block_id"))
                for event in events
                if event.slide_id == current_slide.slide_id
                and event.metadata.get("block_id")
            }
            if not state.current_block_id and executed_blocks:
                block_index = len(current_slide.speaker_notes)
                for index, block in enumerate(current_slide.speaker_notes):
                    if block.block_id not in executed_blocks:
                        block_index = index
                        break
            used_anchors = {
                str(event.metadata.get("interaction_id"))
                for event in events
                if event.slide_id == current_slide.slide_id
                and event.metadata.get("interaction_id")
            }
            while (
                anchor_index < len(current_slide.interaction_anchors)
                and current_slide.interaction_anchors[anchor_index].interaction_id in used_anchors
            ):
                anchor_index += 1
        runtime = _Runtime(
            lesson,
            round_item,
            state,
            list(self.personas),
            block_index=block_index,
            anchor_index=anchor_index,
        )
        runtime.pending_event_id = events[-1].event_id if events else None
        self._runs[round_item.id] = runtime
        return state

    async def step(self, round_id: str) -> ClassroomState:
        runtime = self._runs.get(round_id)
        if runtime is None:
            raise ValueError("round runtime is not loaded; call start_round")
        state = runtime.state
        if state.status != "active":
            return state
        slide = runtime.lesson.slides[state.current_slide_index] if state.current_slide_index < len(runtime.lesson.slides) else None
        if slide is None:
            await self._persist_event(runtime, ClassroomEventType.ROUND_COMPLETED, "Round completed", actor_id="system", actor_role="system")
            await self._persist_state(runtime, phase="round_complete", status="completed")
            return runtime.state
        if state.phase == "slide_enter":
            await self._persist_event(runtime, ClassroomEventType.SLIDE_ENTERED, slide.title, actor_id="system", actor_role="system", slide_id=slide.slide_id)
            runtime.block_index = 0; runtime.anchor_index = 0
            first_block_id = slide.speaker_notes[0].block_id if slide.speaker_notes else None
            await self._persist_state(
                runtime,
                phase="teacher_act",
                slide_id=slide.slide_id,
                slide_index=state.current_slide_index,
                block_id=first_block_id,
                active_agent_id="teacher",
                interaction_count=0,
                student_question_count=0,
                followup_depth=0,
                turn_count=0,
            )
            return runtime.state
        if state.phase == "teacher_act":
            if state.turn_count >= self.policy.max_turns_per_slide:
                await self._persist_state(runtime, phase="objective_check")
                return runtime.state
            block = slide.speaker_notes[runtime.block_index] if runtime.block_index < len(slide.speaker_notes) else None
            try:
                action = await asyncio.wait_for(
                    self.teacher.act(runtime.round.run_id, runtime.round.round_number, slide, block, await self.repository.list_classroom_events(runtime.round.run_id, runtime.round.id), prompt_context=self._directive_context(runtime)),
                    timeout=45,
                )
            except Exception as exc:
                # A single provider/session failure must not discard the
                # authoritative classroom log or wedge the state machine.
                await self._persist_event(runtime, ClassroomEventType.AGENT_ERROR, f"Teacher Agent failed: {exc}", actor_id="teacher", actor_role="teacher", slide_id=slide.slide_id)
                action = TeacherAction(
                    action_type=TeacherActionType.SUMMARIZE if block and str(block.block_type).lower() == "summary" else TeacherActionType.EXPLAIN,
                    speech=block.content if block else "",
                )
            event_type = {TeacherActionType.EXPLAIN: ClassroomEventType.TEACHER_EXPLANATION, TeacherActionType.SUMMARIZE: ClassroomEventType.TEACHER_SUMMARY, TeacherActionType.ASK_QUESTION: ClassroomEventType.TEACHER_QUESTION, TeacherActionType.FOLLOW_UP: ClassroomEventType.TEACHER_FOLLOWUP, TeacherActionType.FEEDBACK: ClassroomEventType.TEACHER_FEEDBACK, TeacherActionType.ANSWER_STUDENT: ClassroomEventType.TEACHER_ANSWER}[action.action_type]
            event = await self._persist_event(
                runtime,
                event_type,
                action.speech,
                actor_id="teacher",
                actor_role="teacher",
                slide_id=slide.slide_id,
                reply_to=action.reply_to_event_id,
                target_agent_id=action.target_student_id,
                metadata={
                    "knowledge_point_ids": action.knowledge_point_ids,
                    "block_id": block.block_id if block else None,
                },
                virtual_seconds=self.virtual_time.for_block(block) if block else None,
            )
            runtime.pending_event_id = event.event_id
            runtime.block_index += 1
            if (action.action_type == TeacherActionType.EXPLAIN
                    and hasattr(self.students, 'listen')
                    and state.student_question_count < self.policy.max_student_questions_per_slide
                    and state.slide_interaction_count < self.policy.max_interactions_per_slide
                    and state.turn_count + 2 < self.policy.max_turns_per_slide):
                chosen = self.policy.choose_student(runtime.round.scenario_seed, slide.slide_id,
                    runtime.personas, interaction_index=runtime.block_index)
                if chosen:
                    await self._persist_state(runtime, phase='student_initiated_question',
                        active_agent_id=chosen.student_id, turn_count=state.turn_count + 1,
                        block_id=slide.speaker_notes[runtime.block_index].block_id
                        if runtime.block_index < len(slide.speaker_notes) else None)
                    return runtime.state
            next_block_id = (
                slide.speaker_notes[runtime.block_index].block_id
                if runtime.block_index < len(slide.speaker_notes)
                else None
            )
            if action.action_type == TeacherActionType.ASK_QUESTION:
                chosen = self.policy.choose_student(runtime.round.scenario_seed, slide.slide_id, runtime.personas, interaction_index=state.slide_interaction_count, target_level=action.target_student_id)
                await self._persist_state(runtime, phase="wait_student", block_id=next_block_id, active_agent_id=chosen.student_id if chosen else None, interaction_count=state.slide_interaction_count + 1, turn_count=state.turn_count + 1)
            else:
                anchor = (
                    slide.interaction_anchors[runtime.anchor_index]
                    if runtime.anchor_index < len(slide.interaction_anchors)
                    else None
                )
                anchor_is_due = bool(
                    anchor
                    and block
                    and anchor.after_block_id in {None, block.block_id}
                )
                if anchor_is_due and self.policy.should_trigger_question(
                    runtime.round.scenario_seed,
                    slide,
                    runtime.anchor_index,
                    interaction_count=state.slide_interaction_count,
                    student_question_count=state.student_question_count,
                ):
                    await self._persist_state(
                        runtime,
                        phase="interaction_decision",
                        block_id=next_block_id,
                        active_agent_id="teacher",
                        turn_count=state.turn_count + 1,
                    )
                else:
                    if anchor_is_due:
                        runtime.anchor_index += 1
                    await self._persist_state(
                        runtime,
                        phase="teacher_act" if runtime.block_index < len(slide.speaker_notes) else "objective_check",
                        block_id=next_block_id,
                        active_agent_id="teacher",
                        turn_count=state.turn_count + 1,
                    )
            return runtime.state
        if state.phase == "interaction_decision":
            anchor = (
                slide.interaction_anchors[runtime.anchor_index]
                if runtime.anchor_index < len(slide.interaction_anchors)
                else None
            )
            if anchor is None:
                await self._persist_state(
                    runtime,
                    phase="teacher_act" if runtime.block_index < len(slide.speaker_notes) else "objective_check",
                    active_agent_id="teacher",
                )
                return runtime.state
            events = await self.repository.list_classroom_events(runtime.round.run_id, runtime.round.id)
            try:
                action = await asyncio.wait_for(
                    self.teacher.act(
                        runtime.round.run_id,
                        runtime.round.round_number,
                        slide,
                        None,
                        events,
                        prompt_context={
                            "mode": "planned_interaction",
                            "required_action_type": "ASK_QUESTION",
                            "interaction_anchor": anchor.model_dump(mode="json"),
                            "instruction": "根据互动锚点向目标层次学生提出一个清晰问题，不提供答案。",
                            **self._directive_context(runtime),
                        },
                    ),
                    timeout=45,
                )
                speech = action.speech.strip() or anchor.planned_question
            except Exception as exc:
                await self._persist_event(
                    runtime,
                    ClassroomEventType.AGENT_ERROR,
                    f"Teacher Agent failed during planned interaction: {exc}",
                    actor_id="teacher",
                    actor_role="teacher",
                    slide_id=slide.slide_id,
                )
                speech = anchor.planned_question
            chosen = self.policy.choose_student(
                runtime.round.scenario_seed,
                slide.slide_id,
                runtime.personas,
                interaction_index=state.slide_interaction_count,
                target_level=anchor.target_student_level,
            )
            question_event = await self._persist_event(
                runtime,
                ClassroomEventType.TEACHER_QUESTION,
                speech,
                actor_id="teacher",
                actor_role="teacher",
                slide_id=slide.slide_id,
                target_agent_id=chosen.student_id if chosen else None,
                metadata={
                    "interaction_id": anchor.interaction_id,
                    "knowledge_point_ids": anchor.knowledge_point_ids,
                    "target_student_level": anchor.target_student_level,
                },
            )
            runtime.pending_event_id = question_event.event_id
            runtime.anchor_index += 1
            if chosen is None:
                await self._persist_event(
                    runtime,
                    ClassroomEventType.AGENT_ERROR,
                    "No student available for planned interaction",
                    actor_id="system",
                    actor_role="system",
                    slide_id=slide.slide_id,
                )
                await self._persist_state(
                    runtime,
                    phase="teacher_act" if runtime.block_index < len(slide.speaker_notes) else "objective_check",
                    active_agent_id="teacher",
                )
            else:
                await self._persist_state(
                    runtime,
                    phase="wait_student",
                    active_agent_id=chosen.student_id,
                    interaction_count=state.slide_interaction_count + 1,
                    turn_count=state.turn_count + 1,
                )
            return runtime.state
        if state.phase == "student_initiated_question":
            persona = next((p for p in runtime.personas if p.student_id == state.active_agent_id), None) or (runtime.personas[0] if runtime.personas else None)
            if persona is None:
                await self._persist_state(runtime, phase="teacher_act")
                return runtime.state
            try:
                history = await self.repository.list_classroom_events(runtime.round.run_id, runtime.round.id)
                public_events = [e for e in history if e.actor_role in {'teacher', 'student'}]
                current_content = next((e.content for e in reversed(public_events) if e.actor_role == 'teacher'), '')
                action = await asyncio.wait_for(self.students.listen(runtime.round.run_id, runtime.round.round_number, persona, self.cognitive_states.get(persona.student_id, []), current_content, public_events, prompt_context=self._directive_context(runtime, for_student=True)), timeout=45)
            except Exception as exc:
                await self._persist_event(runtime, ClassroomEventType.AGENT_ERROR, str(exc), actor_id=persona.student_id, actor_role="student", slide_id=slide.slide_id)
                action = __import__("backend.classroom.actions", fromlist=["StudentAction"]).StudentAction(action_type=StudentActionType.SILENCE, confidence=0)
            if action.action_type != StudentActionType.QUESTION or not action.content.strip():
                await self._persist_state(runtime, phase='interaction_decision', active_agent_id='teacher')
                return runtime.state
            await self._persist_state(runtime, phase='student_initiated_question',
                student_question_count=state.student_question_count + 1,
                interaction_count=state.slide_interaction_count + 1, turn_count=state.turn_count + 1)
            event_type = ClassroomEventType.STUDENT_QUESTION
            event = await self._persist_event(runtime, event_type, action.content, actor_id=persona.student_id, actor_role="student", slide_id=slide.slide_id, reply_to=runtime.pending_event_id)
            runtime.pending_event_id = event.event_id
            if event_type == ClassroomEventType.STUDENT_QUESTION and self.pause_after_student_question:
                await self._persist_state(runtime, phase="teacher_response", active_agent_id="teacher")
                return await self._pause_for_question(runtime)
            await self._persist_state(runtime, phase="teacher_response", active_agent_id="teacher")
            return runtime.state
        if state.phase == "wait_student":
            persona = next((p for p in runtime.personas if p.student_id == state.active_agent_id), None) or (runtime.personas[0] if runtime.personas else None)
            if persona is None:
                await self._persist_event(runtime, ClassroomEventType.AGENT_ERROR, "No student available", actor_id="system", actor_role="system", slide_id=slide.slide_id)
                await self._persist_state(runtime, phase="objective_check")
                return runtime.state
            try:
                action = await asyncio.wait_for(
                    self.students.act(
                        runtime.round.run_id,
                        runtime.round.round_number,
                        persona,
                        self.cognitive_states.get(persona.student_id, []),
                        slide.title,
                        await self.repository.list_classroom_events(runtime.round.run_id, runtime.round.id),
                        prompt_context={
                            "mode": "answer_teacher",
                            "expected_action": "ANSWER, CLARIFICATION, or SILENCE",
                            "teacher_question_event_id": runtime.pending_event_id,
                            **self._directive_context(runtime, for_student=True),
                        },
                    ),
                    timeout=45,
                )
            except Exception as exc:
                await self._persist_event(runtime, ClassroomEventType.AGENT_ERROR, str(exc), actor_id=persona.student_id, actor_role="student", slide_id=slide.slide_id)
                action = __import__("backend.classroom.actions", fromlist=["StudentAction"]).StudentAction(action_type=StudentActionType.SILENCE, content="", confidence=0, reply_to_event_id=runtime.pending_event_id)
            event_type = {StudentActionType.ANSWER: ClassroomEventType.STUDENT_ANSWER, StudentActionType.QUESTION: ClassroomEventType.STUDENT_QUESTION, StudentActionType.CLARIFICATION: ClassroomEventType.STUDENT_CLARIFICATION, StudentActionType.SILENCE: ClassroomEventType.STUDENT_SILENCE}[action.action_type]
            await self._persist_event(runtime, event_type, action.content, actor_id=persona.student_id, actor_role="student", slide_id=slide.slide_id, reply_to=action.reply_to_event_id or runtime.pending_event_id, metadata={"confidence": action.confidence, "misconception_tags": action.misconception_tags})
            await self._persist_state(runtime, phase="teacher_response", active_agent_id="teacher")
            if event_type == ClassroomEventType.STUDENT_QUESTION and self.pause_after_student_question:
                return await self._pause_for_question(runtime)
            return runtime.state
        if state.phase == "teacher_response":
            events = await self.repository.list_classroom_events(runtime.round.run_id, runtime.round.id)
            student_event = next((e for e in reversed(events) if e.actor_role == 'student' and e.slide_id == slide.slide_id), None)
            try:
                action = await asyncio.wait_for(
                    self.teacher.act(
                        runtime.round.run_id,
                        runtime.round.round_number,
                        slide,
                        None,
                        events,
                        prompt_context={
                            "mode": "respond_to_student",
                            "instruction": (
                                "针对学生刚才的回答或问题，先识别正确部分和缺失或误区，"
                                "再选择追问、反馈或答疑；不要跳到下一页。"
                            ),
                            **self._directive_context(runtime),
                        },
                    ),
                    timeout=45,
                )
            except Exception as exc:
                await self._persist_event(runtime, ClassroomEventType.AGENT_ERROR, f"Teacher Agent failed: {exc}", actor_id="teacher", actor_role="teacher", slide_id=slide.slide_id)
                latest_student_event = next(
                    (event for event in reversed(events) if event.actor_role == "student"),
                    None,
                )
                if latest_student_event and latest_student_event.event_type == ClassroomEventType.STUDENT_QUESTION:
                    fallback_speech = "我已收到这个问题。先把它和当前页的核心概念对应起来，再用一个具体例子说明。"
                    fallback_type = TeacherActionType.ANSWER_STUDENT
                elif latest_student_event and latest_student_event.event_type == ClassroomEventType.STUDENT_SILENCE:
                    fallback_speech = "这个问题暂时没有得到回答。我先给一个与当前知识点直接相关的提示，然后继续讲解。"
                    fallback_type = TeacherActionType.FEEDBACK
                else:
                    fallback_speech = "我已收到你的回答。你已经抓住了部分关键信息，还需要结合当前知识点核对适用条件。"
                    fallback_type = TeacherActionType.FEEDBACK
                action = TeacherAction(
                    action_type=fallback_type,
                    speech=fallback_speech,
                    feedback_evaluation=FeedbackEvaluation(quality="UNKNOWN"),
                )
            event_type = {TeacherActionType.FOLLOW_UP: ClassroomEventType.TEACHER_FOLLOWUP, TeacherActionType.FEEDBACK: ClassroomEventType.TEACHER_FEEDBACK, TeacherActionType.ANSWER_STUDENT: ClassroomEventType.TEACHER_ANSWER, TeacherActionType.SUMMARIZE: ClassroomEventType.TEACHER_SUMMARY, TeacherActionType.EXPLAIN: ClassroomEventType.TEACHER_EXPLANATION, TeacherActionType.ASK_QUESTION: ClassroomEventType.TEACHER_QUESTION}[action.action_type]
            teacher_event = await self._persist_event(runtime, event_type, action.speech, actor_id="teacher", actor_role="teacher", slide_id=slide.slide_id, reply_to=events[-1].event_id if events else None)
            if action.feedback_evaluation and student_event and student_event.event_type in {ClassroomEventType.STUDENT_ANSWER, ClassroomEventType.STUDENT_CLARIFICATION}:
                await self._update_cognitive_state(runtime, student_event, action.feedback_evaluation.quality, action.feedback_evaluation.misconception_tags, action.feedback_evaluation.resolved_misconception_tags, slide)
            if action.action_type == TeacherActionType.FOLLOW_UP and self.policy.allow_followup(state.followup_depth, state.turn_count):
                runtime.pending_event_id = teacher_event.event_id
                await self._persist_state(runtime, phase="wait_student", active_agent_id=student_event.actor_id if student_event else None, followup_depth=state.followup_depth + 1, turn_count=state.turn_count + 1)
            else:
                next_block_id = (
                    slide.speaker_notes[runtime.block_index].block_id
                    if runtime.block_index < len(slide.speaker_notes)
                    else None
                )
                await self._persist_state(
                    runtime,
                    phase="interaction_decision" if student_event and student_event.event_type == ClassroomEventType.STUDENT_QUESTION and runtime.anchor_index < len(slide.interaction_anchors) else ("teacher_act" if runtime.block_index < len(slide.speaker_notes) else "objective_check"),
                    block_id=next_block_id,
                    active_agent_id="teacher",
                    followup_depth=0,
                )
            return runtime.state
        if state.phase == "objective_check":
            await self._persist_state(runtime, phase="slide_complete", active_agent_id="system")
            return runtime.state
        if state.phase == "slide_complete":
            await self._persist_event(runtime, ClassroomEventType.SLIDE_COMPLETED, slide.title, actor_id="system", actor_role="system", slide_id=slide.slide_id)
            # 离开该页 → 本页范围的指令自动落实
            await self._resolve_directives_for_scope(runtime, "slide")
            if self.on_slide_completed is not None:
                try:
                    await self.on_slide_completed(runtime.lesson, runtime.round, slide)
                except Exception:
                    # Evaluation is post-processing; a supervisor outage must
                    # not corrupt or stop the classroom event stream.
                    pass
            next_index = state.current_slide_index + 1
            await self._persist_state(runtime, phase="slide_enter" if next_index < len(runtime.lesson.slides) else "round_complete", slide_index=next_index, status="active" if next_index < len(runtime.lesson.slides) else "completed")
            if next_index >= len(runtime.lesson.slides):
                # 本轮结束 → 本轮范围的指令自动落实(整节课范围的留给定稿)
                await self._resolve_directives_for_scope(runtime, "round")
                await self._persist_event(runtime, ClassroomEventType.ROUND_COMPLETED, "Round completed", actor_id="system", actor_role="system")
                if self.on_round_completed is not None:
                    try:
                        await self.on_round_completed(runtime.lesson, runtime.round)
                    except Exception:
                        pass
            return runtime.state
        return state

    async def run_round(self, round_id: str) -> ClassroomState:
        while self._runs[round_id].state.status == "active":
            await self.step(round_id)
        return self._runs[round_id].state

    async def _pause_for_question(self, runtime: _Runtime) -> ClassroomState:
        """「学生提问后暂停」: 停在 teacher_response 之前, 等教师输入。"""
        runtime.resume_phase = "teacher_response"
        runtime.paused_for_question = True
        await self._persist_event(
            runtime,
            ClassroomEventType.ROUND_PAUSED,
            "学生提问后按你的设置暂停，等待你的介入",
            actor_id="system",
            actor_role="system",
        )
        await self._persist_state(runtime, phase="paused", status="paused")
        return runtime.state

    async def pause(self, round_id: str) -> ClassroomState:
        runtime = self._runs[round_id]
        if runtime.state.status == "active":
            runtime.resume_phase = runtime.state.phase
            await self._persist_event(runtime, ClassroomEventType.ROUND_PAUSED, "Round paused", actor_id="system", actor_role="system")
            await self._persist_state(runtime, phase="paused", status="paused")
        return runtime.state

    async def resume(self, round_id: str) -> ClassroomState:
        runtime = self._runs[round_id]
        if runtime.state.status == "paused":
            # If an in-flight Agent action reached its event boundary after the
            # pause request, its persisted phase is the most accurate cursor.
            next_phase = runtime.state.phase if runtime.state.phase != "paused" else (runtime.resume_phase or "teacher_act")
            await self._persist_event(runtime, ClassroomEventType.ROUND_RESUMED, "Round resumed", actor_id="system", actor_role="system")
            await self._persist_state(runtime, phase=next_phase, status="active")
            runtime.resume_phase = None
            runtime.paused_for_question = False
        return runtime.state

    async def intervene(
        self,
        round_id: str,
        content: str,
        *,
        intent: str = "question",
        scope: str = "round",
    ) -> tuple[ClassroomEvent, ClassroomEvent, ClassroomState, TeacherDirective | None]:
        """Persist a teacher intervention, answer it, and register it as a directive.

        Interventions are accepted only while paused. The integration boundary
        first waits for the current Agent action to reach a persisted boundary,
        so user input cannot race a classroom turn or create synthetic UI-only
        messages.

        question 意图只回答一次, 不注册指令; require/correct 注册为生效指令,
        后续每次 agent 调用都会带上它(约束继承), correct 还会由 integration 生成补丁。
        """
        runtime = self._runs[round_id]
        message = content.strip()
        if not message:
            raise ValueError("intervention content must not be empty")
        if runtime.state.status != "paused":
            raise ValueError("classroom must be paused before intervention")
        if runtime.state.current_slide_index >= len(runtime.lesson.slides):
            raise ValueError("classroom round is already complete")
        slide = runtime.lesson.slides[runtime.state.current_slide_index]
        user_event = await self._persist_event(
            runtime,
            ClassroomEventType.USER_INTERVENTION,
            message,
            actor_id="user:teacher",
            actor_role="user",
            slide_id=slide.slide_id,
            target_agent_id="teacher",
            metadata={"source": "classroom_workspace", "intent": intent, "scope": scope},
        )
        directive: TeacherDirective | None = None
        if intent in ("correct", "require"):
            directive = await self._register_directive(runtime, user_event, message, intent, scope, slide.slide_id)
        events = await self.repository.list_classroom_events(runtime.round.run_id, runtime.round.id)
        try:
            action = await asyncio.wait_for(
                self.teacher.act(
                    runtime.round.run_id,
                    runtime.round.round_number,
                    slide,
                    None,
                    events,
                    prompt_context={
                        "mode": "user_intervention",
                        "instruction": (
                            "直接回应教师用户刚刚的课堂介入，不切换 Slide。"
                            "若意图是「纠正」或「要求」，明确说明你会如何在后续讲解中执行；"
                            "不要只复述用户的话。"
                        ),
                        "intervention_event_id": user_event.event_id,
                        "intervention_intent": intent,
                        **self._directive_context(runtime),
                    },
                ),
                timeout=45,
            )
            speech = action.speech.strip()
        except Exception as exc:
            await self._persist_event(
                runtime,
                ClassroomEventType.AGENT_ERROR,
                f"Teacher Agent failed during intervention: {exc}",
                actor_id="teacher",
                actor_role="teacher",
                slide_id=slide.slide_id,
            )
            speech = "教师 Agent 暂时未能处理这条课堂介入，请稍后重试。"
        teacher_event = await self._persist_event(
            runtime,
            ClassroomEventType.TEACHER_ANSWER,
            speech or "已收到这条课堂介入。",
            actor_id="teacher",
            actor_role="teacher",
            slide_id=slide.slide_id,
            reply_to=user_event.event_id,
            target_agent_id="user:teacher",
            metadata={"intervention": True},
        )
        runtime.pending_event_id = teacher_event.event_id
        return user_event, teacher_event, runtime.state, directive

    async def _register_directive(
        self,
        runtime: _Runtime,
        source_event: ClassroomEvent,
        content: str,
        intent: str,
        scope: str,
        slide_id: str | None,
    ) -> TeacherDirective:
        """注册一条生效指令; 同范围的旧修正类指令被标记 superseded(新指令覆盖旧指令)。

        只对 correct/require 生效：提问类指令是课堂问答记录，不是对后续讲解的约束，
        把旧的提问标成 superseded 会让复盘页显示"被覆盖"而语义并不成立。
        """
        if intent in ("correct", "require"):
            for existing in runtime.active_directives:
                if (
                    existing.scope == scope
                    and existing.status == "active"
                    and existing.intent in ("correct", "require")
                ):
                    existing.status = "superseded"
                    existing.resolved_at = utc_now()
                    await self.repository.save_teacher_directive(existing)
        directive = TeacherDirective(
            run_id=runtime.round.run_id,
            round_id=runtime.round.id,
            slide_id=slide_id,
            source_event_id=source_event.event_id,
            content=content,
            intent=intent,
            scope=scope,
        )
        await self.repository.save_teacher_directive(directive)
        runtime.active_directives = [
            item for item in runtime.active_directives if item.status == "active"
        ]
        runtime.active_directives.append(directive)
        return directive

    async def cancel_directive(self, run_id: str, directive_id: str) -> TeacherDirective:
        """教师撤销一条未落实的指令。

        指令只会沿 slide/round/lesson 边界自动落实；若教师发现说错了、或课堂不再需要
        这条约束，过去没有任何撤销入口，它会在本轮剩余的所有 Agent 调用里持续生效。
        """
        directive = await self.repository.get_teacher_directive(directive_id)
        if directive is None or directive.run_id != run_id:
            raise KeyError("教师指令不存在")
        if directive.status != "active":
            raise ValueError("该指令已经落实或被覆盖，无需撤销")
        directive.status = "cancelled"
        directive.resolved_at = utc_now()
        await self.repository.save_teacher_directive(directive)
        runtime = self._runs.get(directive.round_id)
        if runtime is not None:
            runtime.active_directives = [
                item for item in runtime.active_directives if item.directive_id != directive_id
            ]
        return directive

    def _directive_context(self, runtime: _Runtime, *, for_student: bool = False) -> dict[str, Any]:
        """把生效指令转成 prompt 上下文。

        学生只看到「对课堂形式的要求」(如"多提问"), 不接收具体内容纠正, 避免学生行为失真。
        """
        active = [item for item in runtime.active_directives if item.status == "active"]
        if not active:
            return {}
        active = active[-5:]  # 只保留最近 5 条, 防止 prompt 无限膨胀
        if for_student:
            active = [item for item in active if item.intent == "require"]
            if not active:
                return {}
        return {
            "teacher_directives": [
                {"directive_id": item.directive_id, "intent": item.intent, "scope": item.scope, "content": item.content}
                for item in active
            ],
        }

    async def _resolve_directives_for_scope(self, runtime: _Runtime, scope: str) -> int:
        """按范围落实指令: 离开页(slide)/本轮结束(round)/定稿(lesson)。"""
        count = await self.repository.resolve_teacher_directives(
            runtime.round.run_id, round_id=runtime.round.id, scope=scope
        )
        if count:
            runtime.active_directives = [
                item for item in runtime.active_directives
                if not (item.scope == scope and item.status == "active")
            ]
        return count

    async def stop(self, round_id: str) -> ClassroomState:
        runtime = self._runs[round_id]
        if runtime.state.status not in {"completed", "stopped"}:
            await self._persist_event(runtime, ClassroomEventType.ROUND_STOPPED, "Round stopped", actor_id="system", actor_role="system")
            await self._persist_state(runtime, phase="stopped", status="stopped")
        return runtime.state

    async def _persist_event(self, runtime: _Runtime, event_type: ClassroomEventType, content: str, *, actor_id: str, actor_role: str, slide_id: str | None = None, reply_to: str | None = None, target_agent_id: str | None = None, metadata: dict[str, Any] | None = None, virtual_seconds: int | None = None) -> ClassroomEvent:
        delta = virtual_seconds if virtual_seconds is not None else self.virtual_time.for_event(event_type.value, content)
        runtime.state.virtual_elapsed_seconds += delta
        event = ClassroomEvent(run_id=runtime.round.run_id, round_id=runtime.round.id, slide_id=slide_id, actor_id=actor_id, actor_role=actor_role, event_type=event_type, content=content, reply_to=reply_to, target_agent_id=target_agent_id, metadata=metadata or {}, virtual_timestamp=runtime.state.virtual_elapsed_seconds)
        saved = await self.repository.append_classroom_event(event)
        if self.on_event is not None:
            try:
                await self.on_event(saved)
            except Exception:
                # Event fan-out must never lose the authoritative classroom log.
                pass
        return saved

    async def _update_cognitive_state(self, runtime: _Runtime, student_event: ClassroomEvent, quality: str, misconception_tags: list[str], resolved_tags: list[str], slide) -> None:
        student_id = student_event.actor_id
        states = self.cognitive_states.setdefault(student_id, [])
        point_ids = list(slide.knowledge_points) or ["general"]
        by_point = {item.knowledge_point_id: item for item in states}
        delta = {"CORRECT": 0.12, "PARTIAL": 0.06, "INCORRECT": -0.04, "UNKNOWN": 0.0}.get(str(quality).upper(), 0.0)
        for point_id in point_ids:
            current = by_point.get(point_id) or StudentCognitiveState(round_id=runtime.round.id, student_id=student_id, knowledge_point_id=point_id, current_mastery=.5, current_confidence=.5)
            updated = current.model_copy(update={"current_mastery": min(1, max(0, current.current_mastery + delta)), "current_confidence": min(1, max(0, current.current_confidence + delta)), "misconceptions": sorted(set(current.misconceptions).union(misconception_tags) - set(resolved_tags)), "resolved_misconceptions": sorted(set(current.resolved_misconceptions).union(resolved_tags)), "last_event_id": student_event.event_id})
            by_point[point_id] = updated
            await self.repository.save_student_cognitive_state(updated)
        self.cognitive_states[student_id] = list(by_point.values())

    async def _persist_state(
        self,
        runtime: _Runtime,
        *,
        phase: str,
        status: str | None = None,
        slide_id: str | None = None,
        slide_index: int | None = None,
        block_id: str | None | object = _UNSET,
        active_agent_id: str | None = None,
        interaction_count: int | None = None,
        student_question_count: int | None = None,
        followup_depth: int | None = None,
        turn_count: int | None = None,
    ) -> None:
        current = runtime.state
        runtime.state = current.model_copy(update={
            "phase": phase,
            "status": status or current.status,
            "current_slide_id": slide_id if slide_id is not None else current.current_slide_id,
            "current_slide_index": slide_index if slide_index is not None else current.current_slide_index,
            "current_block_id": current.current_block_id if block_id is _UNSET else block_id,
            "active_agent_id": active_agent_id if active_agent_id is not None else current.active_agent_id,
            "slide_interaction_count": interaction_count if interaction_count is not None else current.slide_interaction_count,
            "student_question_count": student_question_count if student_question_count is not None else current.student_question_count,
            "followup_depth": followup_depth if followup_depth is not None else current.followup_depth,
            "turn_count": turn_count if turn_count is not None else current.turn_count,
            "version": current.version + 1,
        })
        await self.repository.save_classroom_state(runtime.state)
