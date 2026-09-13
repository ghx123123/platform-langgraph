from backend.classroom.agent_services import _normalize_student_action, _normalize_teacher_action
from backend.classroom.agent_services import StudentAgentService, TeacherAgentService
from backend.classroom.models import ClassroomAgentInstance, LessonSlide, SpeakerNoteBlock, StudentPersona
from backend.classroom.repository import ClassroomRepository
import pytest


def test_teacher_legacy_speak_is_normalized_without_workflow_fields():
    block = SpeakerNoteBlock(
        block_id="slide_001:block_001", order=1, block_type="explanation",
        content="讲解", estimated_seconds=30,
    )
    result = _normalize_teacher_action({
        "action_type": "speak", "speech": "开始讲解", "block_id": block.block_id,
        "estimated_seconds": 30, "next_action": "speak", "next_block_id": "slide_001:block_002",
    }, block)
    assert result == {"action_type": "EXPLAIN", "speech": "开始讲解"}


def test_teacher_speak_uses_summary_for_summary_block():
    block = SpeakerNoteBlock(
        block_id="slide_001:block_002", order=2, block_type="summary",
        content="总结", estimated_seconds=20,
    )
    assert _normalize_teacher_action({"action_type": "speak", "content": "小结"}, block) == {
        "action_type": "SUMMARIZE", "speech": "小结",
    }


def test_student_known_alias_is_normalized_and_private_control_is_dropped():
    assert _normalize_student_action({
        "action_type": "respond", "speech": "我认为是 A", "next_agent": "teacher",
    }) == {"action_type": "ANSWER", "content": "我认为是 A"}


def test_teacher_feedback_quality_string_is_normalized_to_structured_evaluation():
    result = _normalize_teacher_action({
        "action_type": "feedback",
        "speech": "你的判断正确。",
        "feedback_evaluation": "correct",
    }, None)

    assert result["action_type"] == "FEEDBACK"
    assert result["feedback_evaluation"] == {"quality": "CORRECT"}


@pytest.mark.asyncio
async def test_saved_role_prompt_is_injected_into_teacher_and_student_context(tmp_path):
    class Runtime:
        def __init__(self):
            self.prompts = []

        async def generate(self, *args, **kwargs):
            self.prompts.append(args[4])
            return '{"action_type":"EXPLAIN","speech":"ok"}' if args[2] == "teacher" else '{"action_type":"SILENCE"}'

    repo = ClassroomRepository(tmp_path / "role-context.db")
    await repo.initialize()
    await repo.save_agent_instance(ClassroomAgentInstance(
        run_id="run-role", agent_key="teacher", role="teacher", display_name="Teacher",
        config={"role_profile": {"role_definition": "耐心教师", "system_prompt": "先举例后追问"}},
    ))
    await repo.save_agent_instance(ClassroomAgentInstance(
        run_id="run-role", agent_key="student:low", role="student", display_name="Basic",
        config={"role_profile": {"role_definition": "谨慎学生", "system_prompt": "不确定时说明"}},
    ))
    runtime = Runtime()
    slide = LessonSlide(slide_id="slide_001", order=1, title="Demo", speaker_notes=[{
        "block_id": "slide_001:block_001", "order": 1, "block_type": "explanation",
        "content": "Explain", "estimated_seconds": 10,
    }])
    teacher_action = await TeacherAgentService(runtime, repo).act(
        "run-role", 1, slide, slide.speaker_notes[0], [],
    )
    persona = StudentPersona(
        run_id="run-role", student_id="student:low", name="Basic", level="low",
        ability=.3, engagement=.5, confidence=.4, verbosity=.4,
        question_propensity=.2, answer_propensity=.5, scenario_seed="seed",
    )
    await StudentAgentService(runtime, repo).act(
        "run-role", 1, persona, [], "Demo", [],
    )
    assert teacher_action.action_type.value == "EXPLAIN"
    assert "耐心教师" in runtime.prompts[0]
    assert "谨慎学生" in runtime.prompts[1]
