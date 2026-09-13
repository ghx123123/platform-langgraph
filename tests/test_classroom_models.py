from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.classroom.models import (
    ClassroomEvent,
    LessonSlide,
    LessonVersion,
    RevisionPatch,
    SpeakerNoteBlock,
    StudentCognitiveState,
    StudentPersona,
    StudentScenarioBaseline,
)


def test_lesson_blueprint_keeps_stable_slide_and_block_ids() -> None:
    slide = LessonSlide(
        slide_id="slide-1",
        order=1,
        title="Introduction",
        speaker_notes=[
            SpeakerNoteBlock(block_id="block-1", order=1, content="Explain the concept")
        ],
    )
    lesson = LessonVersion(
        lesson_id="lesson-1",
        run_id="run-1",
        version_number=1,
        title="Demo",
        slides=[slide],
    )

    assert lesson.slides[0].slide_id == "slide-1"
    assert lesson.slides[0].speaker_notes[0].block_id == "block-1"


def test_models_reject_invalid_ranges_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        StudentPersona(
            run_id="run-1",
            student_id="student-1",
            name="Student",
            level="low",
            ability=1.2,
            engagement=0.5,
            confidence=0.5,
            verbosity=0.5,
            question_propensity=0.5,
            answer_propensity=0.5,
            scenario_seed="seed",
        )

    with pytest.raises(ValidationError):
        LessonSlide(slide_id="slide-1", order=1, title="x", unexpected=True)


def test_student_baseline_and_runtime_state_are_separate_round_entities() -> None:
    baseline = StudentScenarioBaseline(
        run_id="run-1",
        student_id="student-1",
        initial_mastery={"kp-1": 0.2},
        initial_confidence={"kp-1": 0.4},
        initial_misconceptions={"kp-1": ["operator-confusion"]},
        prior_knowledge={"python": "basic"},
        scenario_seed="seed-42",
    )
    state = StudentCognitiveState(
        round_id="round-2",
        student_id="student-1",
        knowledge_point_id="kp-1",
        current_mastery=0.8,
        current_confidence=0.7,
        misconceptions=["operator-confusion"],
    )

    assert baseline.scenario_seed == "seed-42"
    assert state.round_id == "round-2"
    assert state.current_mastery != baseline.initial_mastery["kp-1"]

    compact = StudentCognitiveState(
        round_id="round-2",
        student_id="student-1",
        knowledge_point_id="kp-1",
        mastery=0.6,
        confidence=0.6,
    )
    assert compact.current_mastery == compact.mastery == 0.6


def test_event_keeps_virtual_and_real_timestamps_distinct() -> None:
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = ClassroomEvent(
        run_id="run-1",
        round_id="round-1",
        actor_id="teacher",
        actor_role="teacher",
        event_type="teacher.explanation",
        virtual_timestamp=95,
        created_at=created,
    )

    assert event.virtual_timestamp == 95
    assert event.created_at == created


def test_revision_patch_contains_provenance() -> None:
    patch = RevisionPatch(
        run_id="run-1",
        source_version_id="v1",
        target_version_id="v2",
        source_round_id="round-1",
        target_type="speaker_note",
        slide_id="slide-6",
        block_id="b3",
        field_path="content",
        before="old explanation",
        after="corrected explanation",
        reason="Low-level student confused assignment and comparison operators",
        source_observation_ids=["obs-12"],
    )

    assert patch.source_observation_ids == ["obs-12"]
    assert patch.before != patch.after
