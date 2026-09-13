"""Evidence-based Supervisor evaluation for classroom_v2 (Phase 5).

The service is deliberately passive: it reads lesson/events and writes only
observations and reports.  It never emits ClassroomEvent speech or mutates a
ClassroomState.  A generator may be injected for a real DSH supervisor; the
deterministic fallback keeps tests and offline operation key-free.
"""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from .models import (
    ClassroomEvent,
    LessonSlide,
    SimulationRound,
    SupervisorObservation,
    SupervisorReport,
)
from .prompts import DEFAULT_SUPERVISOR_PROFILE, build_supervisor_observation_prompt, build_supervisor_report_prompt
from .repository import ClassroomRepository


DIMENSION_WEIGHTS: dict[str, float] = {
    "content_accuracy": 0.15,
    "objective_achievement": 0.15,
    "explanation_clarity": 0.15,
    "interaction_quality": 0.10,
    "questioning_quality": 0.10,
    "feedback_quality": 0.10,
    "misconception_handling": 0.10,
    "pacing": 0.075,
    "ppt_speech_alignment": 0.075,
}

Generator = Callable[[str, str], Awaitable[Any]]


class EvaluationError(ValueError):
    pass


class SupervisorEvaluationService:
    """Build slide observations and round reports from persisted classroom facts."""

    def __init__(self, repository: ClassroomRepository, generator: Generator | None = None, runtime: Any | None = None) -> None:
        self.repository = repository
        self.generator = generator
        self.runtime = runtime

    async def _supervisor_profile(self, run_id: str) -> dict[str, Any]:
        """Read only this run's editable supervisor configuration."""
        instance = await self.repository.get_agent_instance(run_id, "supervisor")
        profile = dict(DEFAULT_SUPERVISOR_PROFILE)
        if instance and isinstance(instance.config, dict):
            configured = instance.config.get("supervisor_profile")
            if isinstance(configured, dict):
                profile.update(configured)
        if not isinstance(profile.get("evaluation_focus"), list):
            profile["evaluation_focus"] = list(DEFAULT_SUPERVISOR_PROFILE["evaluation_focus"])
        return profile

    async def evaluate_slide(
        self,
        run_id: str,
        round_item: SimulationRound,
        slide: LessonSlide,
        events: Sequence[ClassroomEvent] | None = None,
        *,
        student_public_state: Any | None = None,
        directives: Sequence[Any] | None = None,
    ) -> SupervisorObservation:
        self._check_run(run_id, round_item)
        all_events = list(events) if events is not None else await self.repository.list_classroom_events(run_id, round_item.id)
        slide_events = [e for e in all_events if e.run_id == run_id and e.round_id == round_item.id and e.slide_id == slide.slide_id]
        if not slide_events:
            raise EvaluationError(f"no classroom events found for slide {slide.slide_id}")
        valid_ids = {event.event_id for event in slide_events}
        directive_list = list(directives or [])
        context = {
            "round_id": round_item.id,
            "slide": slide.model_dump(mode="json"),
            "events": [event.model_dump(mode="json") for event in slide_events],
            "student_public_state": student_public_state,
            "supervisor_profile": await self._supervisor_profile(run_id),
            # 教师课堂上明确下达的指令: 督导要逐条判定是否被遵守
            "teacher_directives": [
                {"directive_id": item.directive_id, "intent": item.intent, "scope": item.scope, "content": item.content}
                for item in directive_list
            ],
        }
        payload: dict[str, Any] | None = None
        if self.generator is not None:
            system, user = build_supervisor_observation_prompt(context)
            raw = await self.generator(system, user)
            payload = _parse_json(raw)
        elif self.runtime is not None:
            system, user = build_supervisor_observation_prompt(context)
            raw = await self.runtime.generate(run_id, round_item.round_number, "supervisor", system, user)
            payload = _parse_json(raw)
        if payload is None:
            payload = self._fallback_slide(slide, slide_events)
        elif self._is_unusable_observation(payload, slide):
            # A syntactically valid model response is still unusable when it
            # merely restates that evidence exists. The review UI must show a
            # concrete judgment that can drive a revision decision.
            payload = self._fallback_slide(slide, slide_events)
        event_ids = list(payload.get("event_ids") or [])
        if not event_ids:
            # The fallback and a model are both required to ground an observation.
            event_ids = [event.event_id for event in slide_events[: min(3, len(slide_events))]]
        unknown = set(event_ids) - valid_ids
        if unknown:
            raise EvaluationError(f"observation references unknown event ids: {sorted(unknown)}")
        analysis = payload.get("analysis")
        if not isinstance(analysis, dict) or not analysis:
            analysis = self._derive_analysis(slide, slide_events)
        else:
            analysis = {str(key): str(value) for key, value in analysis.items() if str(value).strip()}
            analysis = {**self._derive_analysis(slide, slide_events), **analysis}
        # 指令遵循度: 模型逐条判定; 未遵守的写进 analysis, 并在下方补一条 alignment observation
        compliance = self._normalize_compliance(payload.get("directive_compliance"), directive_list)
        if compliance:
            analysis = {**analysis, "directive_compliance": json.dumps(compliance, ensure_ascii=False)}
        observation = SupervisorObservation(
            round_id=round_item.id,
            slide_id=slide.slide_id,
            event_ids=event_ids,
            category=payload.get("category", "other"),
            severity=payload.get("severity", "info"),
            issue=str(payload["issue"]),
            evidence=self._evidence_with_slide_context(slide, payload.get("evidence"), slide_events),
            recommendation=str(payload["recommendation"]),
            analysis=analysis,
        )
        await self.repository.save_supervisor_observation(observation)
        # 未遵守的教师指令额外落一条 alignment observation, 让复盘页能直接看到
        violations = [item for item in compliance if not item.get("followed")]
        for violation in violations:
            directive = next((d for d in directive_list if d.directive_id == violation.get("directive_id")), None)
            content = directive.content if directive is not None else "教师指令"
            await self.repository.save_supervisor_observation(SupervisorObservation(
                round_id=round_item.id,
                slide_id=slide.slide_id,
                event_ids=event_ids,
                category="alignment",
                severity="major",
                issue=f"教师课堂上明确要求「{content}」，本页未落实。",
                evidence=str(violation.get("evidence") or "督导未在事件中找到执行该指令的痕迹。"),
                recommendation=f"在下一版讲解中落实教师指令：{content}",
                analysis={"directive_id": directive.directive_id if directive is not None else "", "source": "teacher_directive"},
            ))
        return observation

    @staticmethod
    def _normalize_compliance(raw: Any, directives: Sequence[Any]) -> list[dict[str, Any]]:
        """只接受引用了真实 directive_id 的判定, 防止模型编造指令。"""
        if not isinstance(raw, list) or not directives:
            return []
        valid = {item.directive_id for item in directives}
        result: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            directive_id = str(item.get("directive_id") or "").strip()
            if directive_id not in valid:
                continue
            result.append({
                "directive_id": directive_id,
                "followed": bool(item.get("followed", True)),
                "evidence": str(item.get("evidence") or "").strip()[:500],
            })
        return result

    async def evaluate_round(
        self,
        run_id: str,
        round_item: SimulationRound,
        lesson_objectives: list[str] | None = None,
        *,
        events: Sequence[ClassroomEvent] | None = None,
        observations: Sequence[SupervisorObservation] | None = None,
    ) -> SupervisorReport:
        self._check_run(run_id, round_item)
        event_list = list(events) if events is not None else await self.repository.list_classroom_events(run_id, round_item.id)
        obs_list = list(observations) if observations is not None else await self.repository.list_supervisor_observations(round_item.id)
        for obs in obs_list:
            if obs.round_id != round_item.id:
                raise EvaluationError("observation does not belong to the current round")
            if any(event_id not in {event.event_id for event in event_list} for event_id in obs.event_ids):
                raise EvaluationError(f"observation {obs.observation_id} contains unknown event evidence")
        context = {
            "round_id": round_item.id,
            "lesson_objectives": lesson_objectives or [],
            "observations": [o.model_dump(mode="json") for o in obs_list],
            "key_events": [e.model_dump(mode="json") for e in event_list if _event_value(e).endswith(("teacher.feedback", "student.answer", "slide.completed"))],
            "round_summary": {"event_count": len(event_list), "observation_count": len(obs_list)},
            "supervisor_profile": await self._supervisor_profile(run_id),
        }
        payload: dict[str, Any] | None = None
        if self.generator is not None:
            system, user = build_supervisor_report_prompt(context)
            payload = _parse_json(await self.generator(system, user))
        elif self.runtime is not None:
            system, user = build_supervisor_report_prompt(context)
            payload = _parse_json(await self.runtime.generate(run_id, round_item.round_number, "supervisor", system, user))
        if payload is not None and self._is_unusable_report(payload, obs_list):
            # Do not persist a numerically complete but evidence-free report.
            # This is common when a provider echoes the JSON schema with one
            # default score for every dimension and no actionable finding.
            payload = self._fallback_report(obs_list, event_list)
        if payload is None:
            payload = self._fallback_report(obs_list, event_list)
        raw_scores = payload.get("dimension_scores") or {}
        missing_dimensions = set(DIMENSION_WEIGHTS) - set(raw_scores)
        if missing_dimensions:
            raise EvaluationError(
                "supervisor report is missing dimension scores: "
                + ", ".join(sorted(missing_dimensions))
            )
        scores = {name: _score(raw_scores.get(name, 70)) for name in DIMENSION_WEIGHTS}
        overall = round(sum(scores[name] * weight for name, weight in DIMENSION_WEIGHTS.items()))
        referenced = list(payload.get("observation_ids") or payload.get("observations") or [o.observation_id for o in obs_list])
        valid_obs = {o.observation_id for o in obs_list}
        if set(referenced) - valid_obs:
            raise EvaluationError("report references an observation from another round")
        critical_issues = [str(x) for x in payload.get("critical_issues") or []]
        revision_priorities = [str(x) for x in payload.get("revision_priorities") or []]
        for observation in obs_list:
            if observation.observation_id not in referenced:
                continue
            evidence_label = f"{observation.slide_id}（证据：{', '.join(observation.event_ids[:3])}）"
            if observation.severity in {"major", "critical"} and not any(observation.issue in item for item in critical_issues):
                critical_issues.append(f"{evidence_label} {observation.issue}")
            if observation.severity in {"minor", "major", "critical"} and not any(observation.recommendation in item for item in revision_priorities):
                revision_priorities.append(f"{evidence_label} {observation.recommendation}")
        report = SupervisorReport(
            run_id=run_id,
            round_id=round_item.id,
            overall_score=overall,
            dimension_scores=scores,
            strengths=[str(x) for x in payload.get("strengths") or []],
            critical_issues=critical_issues,
            observations=referenced,
            revision_priorities=revision_priorities,
        )
        await self.repository.save_supervisor_report(report)
        return report

    async def build_report(self, *args: Any, **kwargs: Any) -> SupervisorReport:
        return await self.evaluate_round(*args, **kwargs)

    @staticmethod
    def _fallback_slide(slide: LessonSlide, events: list[ClassroomEvent]) -> dict[str, Any]:
        slide_label = f"Slide {slide.order}《{slide.title}》"
        topic_label = "、".join(slide.knowledge_points) or "当前学习目标"
        student_answers = [e for e in events if e.actor_role == "student" and "answer" in _event_value(e)]
        student_questions = [e for e in events if _event_value(e).endswith(("student.question", "student.clarification"))]
        student_silences = [e for e in events if _event_value(e).endswith("student.silence")]
        student_events = student_answers + student_questions + student_silences
        teacher_questions = [e for e in events if _event_value(e).endswith(("teacher.question", "teacher.followup"))]
        teacher_feedback = [e for e in events if _event_value(e).endswith("teacher.feedback")]
        teacher_answers = [e for e in events if _event_value(e).endswith("teacher.answer")]
        if not student_events:
            cited = teacher_questions or [e for e in events if e.actor_role == "teacher"] or events
            return {
                "category": "interaction",
                "severity": "major",
                "event_ids": [e.event_id for e in cited[:3]],
                "issue": f"{slide_label}围绕{topic_label}只有教师讲解事件，没有形成学生回答、提问、澄清或沉默事件，缺少可验证的学习反馈。",
                "evidence": "; ".join(f"{e.event_id}: {e.content}" for e in cited[:3]),
                "recommendation": f"在{slide_label}讲稿结束前加入一个针对{topic_label}的具体问题，指定一名学生回答，并记录教师对正确点、误区和下一步动作的反馈。",
            }
        if student_silences and not (student_answers or student_questions):
            return {
                "category": "interaction",
                "severity": "major",
                "event_ids": [e.event_id for e in (teacher_questions + student_silences)[:3]],
                "issue": f"{slide_label}虽发起互动，但学生只产生沉默事件，未获得可判断{topic_label}理解程度的回答。",
                "evidence": "; ".join(f"{e.event_id}: {e.content or '学生沉默'}" for e in (teacher_questions + student_silences)[:3]),
                "recommendation": f"降低{slide_label}问题难度或提供一个与{topic_label}相关的具体提示，再邀请同一学生作答，以获得有效学习证据。",
            }
        if student_answers and not teacher_feedback:
            return {
                "category": "feedback",
                "severity": "major",
                "event_ids": [student_answers[0].event_id],
                "issue": f"{slide_label}中学生已经作答，但没有记录教师针对该答案的明确反馈，无法判断{topic_label}是否被纠正或巩固。",
                "evidence": f"{student_answers[0].event_id}: {student_answers[0].content}",
                "recommendation": f"补充针对{slide_label}的反馈：指出学生回答中关于{topic_label}的正确部分、缺失内容和暴露的误区，并明确下一步学习动作。",
            }
        interaction_chain = teacher_questions + student_answers + student_questions + teacher_feedback + teacher_answers
        return {
            "category": "interaction",
            "severity": "info",
            "event_ids": [e.event_id for e in interaction_chain[:4]],
            "issue": f"{slide_label}围绕{topic_label}形成了可追踪的师生互动与教师回应闭环；学生事件与教师回应均已落到具体事件。",
            "evidence": "; ".join(f"{e.event_id}: {e.content}" for e in interaction_chain[:4]),
            "recommendation": f"保留{slide_label}当前互动位置；下一轮继续依据学生回答中的具体表述调整追问或纠错，并检查其是否覆盖{topic_label}的学习目标。",
        }

    @staticmethod
    def _derive_analysis(slide: LessonSlide, events: Sequence[ClassroomEvent]) -> dict[str, str]:
        """Create a transparent minimum analysis when a provider omits details."""
        values = [_event_value(event) for event in events]
        teacher_content = [event for event in events if event.actor_role == "teacher" and any(token in _event_value(event) for token in ("teacher.explanation", "teacher.summary", "teacher.answer"))]
        student_responses = [event for event in events if event.actor_role == "student" and any(token in _event_value(event) for token in ("student.answer", "student.question", "student.clarification", "student.silence"))]
        feedback = [event for event in events if _event_value(event).endswith(("teacher.feedback", "teacher.followup", "teacher.answer", "teacher.summary"))]
        anchors = ", ".join(anchor.interaction_id for anchor in slide.interaction_anchors) or "无互动锚点"
        return {
            "ppt_alignment": f"本页 PPT 标题为“{slide.ppt_content.title or slide.title}”，知识点：{', '.join(slide.knowledge_points) or '未标注'}；教师内容事件 {len(teacher_content)} 条。",
            "teaching_coverage": f"学习目标：{', '.join(slide.learning_objectives) or '沿用课程目标'}；已记录讲解/总结事件 {len(teacher_content)} 条。",
            "student_response_analysis": f"学生事件 {len(student_responses)} 条；事件类型：{', '.join(sorted(set(values))) if values else '无'}。",
            "feedback_analysis": f"教师反馈/追问/回答/总结事件 {len(feedback)} 条；{'可检查互动闭环' if student_responses and feedback else '没有足够的反馈闭环证据'}。",
            "misconception_analysis": f"预期误区 {len(slide.expected_misconceptions)} 条；互动锚点：{anchors}。需结合学生原话判断是否暴露误区。",
            "objective_evidence": f"依据本页 {len(events)} 条课堂事件和已引用事件 ID 判断，不把模型运行时间当作学习证据。",
        }

    @staticmethod
    def _is_unusable_observation(payload: dict[str, Any], slide: LessonSlide | None = None) -> bool:
        issue = str(payload.get("issue") or "").strip().lower()
        recommendation = str(payload.get("recommendation") or "").strip().lower()
        if not issue or not recommendation:
            return True
        generic_phrases = {
            "slide evidence was recorded.",
            "slide execution events were recorded.",
            "review the cited slide events.",
            "review the cited interaction evidence.",
            "已记录课堂证据。",
            "建议查看相关课堂事件。",
        }
        if issue in generic_phrases or recommendation in generic_phrases:
            return True
        # Short, title-free one-liners are not useful revision evidence even
        # when they are syntactically valid JSON.  A real observation should
        # identify the page or one of its scoped knowledge points.
        if slide is not None:
            anchors = [slide.title.strip().lower(), *(point.strip().lower() for point in slide.knowledge_points)]
            if len(issue) < 24 or len(recommendation) < 24:
                return True
            if anchors and not any(anchor and anchor in issue for anchor in anchors):
                return True
        return False

    @classmethod
    def _is_unusable_report(
        cls,
        payload: dict[str, Any],
        observations: Sequence[SupervisorObservation],
    ) -> bool:
        """Reject schema-shaped reports that contain no review judgment.

        A report may legitimately have no critical issues, but it still needs
        either strengths, revision priorities, or slide-specific observations.
        Only downgrade the response when the observations themselves are
        generic and every dimension was given the same score.
        """
        dimensions = payload.get("dimension_scores")
        if not isinstance(dimensions, dict) or not dimensions:
            return True
        try:
            scores = {float(value) for value in dimensions.values()}
        except (TypeError, ValueError):
            return True
        no_summary = not any(
            payload.get(key)
            for key in ("strengths", "critical_issues", "revision_priorities")
        )
        generic_observations = bool(observations) and all(
            cls._is_unusable_observation(
                {
                    "issue": observation.issue,
                    "recommendation": observation.recommendation,
                }
            )
            for observation in observations
        )
        return no_summary and len(scores) == 1 and (generic_observations or not observations)

    @staticmethod
    def _evidence_with_slide_context(
        slide: LessonSlide,
        evidence: Any,
        events: list[ClassroomEvent],
    ) -> str:
        slide_label = f"Slide {slide.order}《{slide.title}》"
        source = str(evidence or "").strip()
        event_text = "; ".join(f"{event.event_id}: {event.content}" for event in events[:4])
        return f"{slide_label}；知识点：{'、'.join(slide.knowledge_points) or '未标注'}；{source or event_text}；证据事件：{', '.join(event.event_id for event in events[:4])}"

    @staticmethod
    def _fallback_report(
        observations: list[SupervisorObservation],
        events: list[ClassroomEvent],
    ) -> dict[str, Any]:
        """Derive a conservative, non-uniform score from persisted evidence.

        This path is used only when the Supervisor model is unavailable.  It
        intentionally avoids pretending that every dimension is the same and
        keeps content accuracy conservative unless an observation supports it.
        """
        values = [_event_value(event) for event in events]
        explanation_count = sum(value.endswith(("teacher.explanation", "teacher.summary")) for value in values)
        teacher_question_count = sum(value.endswith(("teacher.question", "teacher.followup")) for value in values)
        followup_count = sum(value.endswith("teacher.followup") for value in values)
        feedback_count = sum(value.endswith(("teacher.feedback", "teacher.answer")) for value in values)
        student_answer_count = sum(value.endswith(("student.answer", "student.clarification")) for value in values)
        student_question_count = sum(value.endswith("student.question") for value in values)
        silence_count = sum(value.endswith("student.silence") for value in values)
        completed_slide_count = sum(value.endswith("slide.completed") for value in values)
        round_completed = any(value.endswith("round.completed") for value in values)
        agent_error_count = sum(value.endswith("agent.error") for value in values)

        feedback_coverage = (
            min(1.0, feedback_count / student_answer_count)
            if student_answer_count
            else 0.0
        )
        scores = {
            "content_accuracy": 80,
            "objective_achievement": min(92, 64 + completed_slide_count * 5 + (10 if round_completed else 0)),
            "explanation_clarity": min(90, 68 + explanation_count * 3) - agent_error_count * 4,
            "interaction_quality": min(92, 55 + (student_answer_count + student_question_count) * 7) - silence_count * 4,
            "questioning_quality": min(92, 55 + teacher_question_count * 8 + student_question_count * 4),
            "feedback_quality": 55 + round(feedback_coverage * 32),
            "misconception_handling": min(90, 55 + followup_count * 8 + feedback_count * 5),
            "pacing": (82 if round_completed else 66) - agent_error_count * 3,
            "ppt_speech_alignment": min(90, 72 + explanation_count * 3) - agent_error_count * 3,
        }

        category_dimensions = {
            "content": ("content_accuracy",),
            "accuracy": ("content_accuracy",),
            "objective": ("objective_achievement",),
            "clarity": ("explanation_clarity",),
            "explanation": ("explanation_clarity",),
            "interaction": ("interaction_quality",),
            "questioning": ("questioning_quality",),
            "feedback": ("feedback_quality", "misconception_handling"),
            "misconception": ("misconception_handling",),
            "pacing": ("pacing",),
            "alignment": ("ppt_speech_alignment",),
        }
        severity_penalty = {"info": 0, "minor": 4, "major": 10, "critical": 18}
        for observation in observations:
            targets: set[str] = set()
            category = observation.category.lower()
            for keyword, dimensions in category_dimensions.items():
                if keyword in category:
                    targets.update(dimensions)
            if not targets and observation.severity in {"major", "critical"}:
                targets.add("objective_achievement")
            penalty = severity_penalty.get(observation.severity.lower(), 3)
            for dimension in targets:
                scores[dimension] -= penalty

        scores = {name: max(0, min(100, round(value))) for name, value in scores.items()}
        strengths: list[str] = []
        if scores["ppt_speech_alignment"] >= 82:
            strengths.append("教师讲解按已确认的逐页讲稿执行，PPT 与课堂表达有可追踪对应关系。")
        if scores["interaction_quality"] >= 78:
            strengths.append("本轮形成了可引用的学生回应或主动提问证据。")
        if scores["feedback_quality"] >= 78:
            strengths.append("学生作答后获得了明确的教师反馈。")
        return {
            "dimension_scores": scores,
            "strengths": strengths,
            "critical_issues": [
                observation.issue
                for observation in observations
                if observation.severity in {"major", "critical"}
            ],
            "observation_ids": [observation.observation_id for observation in observations],
            "revision_priorities": [
                observation.recommendation
                for observation in observations
                if observation.severity in {"minor", "major", "critical"}
            ],
        }

    @staticmethod
    def _check_run(run_id: str, round_item: SimulationRound) -> None:
        if round_item.run_id != run_id:
            raise EvaluationError("run_id and round do not match")


def _score(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        raise EvaluationError(f"invalid dimension score: {value!r}")


def _parse_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw).strip(), flags=re.IGNORECASE)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise EvaluationError("supervisor output is not valid JSON")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise EvaluationError("supervisor output must be a JSON object")
    return value


def _event_value(event: ClassroomEvent) -> str:
    value = event.event_type
    return str(getattr(value, "value", value))
