"""SQLite persistence for the classroom_v2 domain.

The repository has no knowledge of LangGraph, DSH, prompts, or WebSockets. It
stores business facts and returns Pydantic domain models. All writes are run in
worker threads so the async API follows the existing repository convention.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from .models import (
    ClassroomAgentInstance,
    ClassroomEvent,
    ClassroomState,
    LessonReviewMessage,
    LessonSlide,
    LessonVersion,
    SimulationRound,
    SpeakerNoteBlock,
    StudentCognitiveState,
    StudentPersona,
    StudentScenarioBaseline,
    SupervisorObservation,
    SupervisorReport,
    RevisionPatch,
    TeacherDirective,
    utc_now,
)

T = TypeVar("T")


class ClassroomRepository:
    """Minimal persistence boundary for Phase 1 classroom entities."""

    migration_names = ("005_classroom_v2.sql", "006_lesson_blueprint_fields.sql", "007_lesson_review_messages.sql", "008_supervisor_observation_analysis.sql", "009_teacher_directives.sql")

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        migration_dir = Path(__file__).resolve().parents[1] / "migrations"
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            for name in self.migration_names:
                migration = migration_dir / name
                if not migration.exists():
                    raise FileNotFoundError(f"Missing classroom migration: {migration}")
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?", (migration.name,)
                ).fetchone()
                if not applied:
                    connection.executescript(migration.read_text(encoding="utf-8"))
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (migration.name, utc_now().isoformat()),
                    )

    async def ensure_run(self, run_id: str, workflow_run_id: str | None = None) -> None:
        await asyncio.to_thread(self._ensure_run_sync, run_id, workflow_run_id)

    def _ensure_run_sync(self, run_id: str, workflow_run_id: str | None) -> None:
        now = utc_now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO classroom_runs(run_id, workflow_run_id, workflow_version, created_at, updated_at)
                   VALUES (?, ?, 'classroom_v2', ?, ?)
                   ON CONFLICT(run_id) DO UPDATE SET workflow_run_id = COALESCE(excluded.workflow_run_id, classroom_runs.workflow_run_id), updated_at = excluded.updated_at""",
                (run_id, workflow_run_id, now, now),
            )

    async def create_lesson_version(self, version: LessonVersion) -> LessonVersion:
        await asyncio.to_thread(self._create_lesson_version_sync, version)
        return version

    async def create_lesson_version_if_absent(self, version: LessonVersion) -> bool:
        """Atomically persist a version number once within its run.

        Returns ``False`` when another worker already committed the same
        ``(run_id, version_number)``.  This is the database-side idempotency
        guard for duplicate browser requests and multi-worker deployments.
        """
        return await asyncio.to_thread(self._create_lesson_version_if_absent_sync, version)

    def _create_lesson_version_if_absent_sync(self, version: LessonVersion) -> bool:
        now = version.updated_at.isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_run_connection(connection, version.run_id)
            existing = connection.execute(
                "SELECT 1 FROM lesson_versions WHERE run_id = ? AND version_number = ?",
                (version.run_id, version.version_number),
            ).fetchone()
            if existing is not None:
                return False
            connection.execute(
                """INSERT INTO lesson_versions
                (id, lesson_id, run_id, version_number, source_version_id, created_from_round_id,
                 title, learning_objectives_json, knowledge_points_json, estimated_minutes, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (version.id, version.lesson_id, version.run_id, version.version_number,
                 version.source_version_id, version.created_from_round_id, version.title,
                 _json(version.learning_objectives), _json(version.knowledge_points), version.estimated_minutes, version.status,
                 version.created_at.isoformat(), now),
            )
            for slide in version.slides:
                self._insert_slide(connection, version.id, slide)
            return True

    def _create_lesson_version_sync(self, version: LessonVersion) -> None:
        now = version.updated_at.isoformat()
        with self._connect() as connection:
            self._ensure_run_connection(connection, version.run_id)
            connection.execute(
                """INSERT INTO lesson_versions
                (id, lesson_id, run_id, version_number, source_version_id, created_from_round_id,
                 title, learning_objectives_json, knowledge_points_json, estimated_minutes, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (version.id, version.lesson_id, version.run_id, version.version_number,
                 version.source_version_id, version.created_from_round_id, version.title,
                 _json(version.learning_objectives), _json(version.knowledge_points), version.estimated_minutes, version.status,
                 version.created_at.isoformat(), now),
            )
            for slide in version.slides:
                self._insert_slide(connection, version.id, slide)

    async def get_lesson_version(self, version_id: str) -> LessonVersion | None:
        row = await asyncio.to_thread(self._get_lesson_version_sync, version_id)
        return self._lesson_from_row(row) if row else None

    def _get_lesson_version_sync(self, version_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM lesson_versions WHERE id = ?", (version_id,)).fetchone()

    async def list_lesson_versions(self, run_id: str) -> list[LessonVersion]:
        rows = await asyncio.to_thread(self._list_lesson_versions_sync, run_id)
        return [self._lesson_from_row(row) for row in rows]

    async def delete_lesson_version(self, version_id: str) -> None:
        """删除一个未进入课堂演练的 LessonVersion 及其全部子记录(用于失败重生成)。"""
        await asyncio.to_thread(self._delete_lesson_version_sync, version_id)

    def _delete_lesson_version_sync(self, version_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            slide_rows = connection.execute(
                "SELECT id FROM lesson_slides WHERE lesson_version_id = ?", (version_id,)
            ).fetchall()
            slide_ids = [row["id"] for row in slide_rows]
            for slide_id in slide_ids:
                for table in ("speaker_note_blocks", "interaction_anchors", "expected_misconceptions"):
                    connection.execute(f"DELETE FROM {table} WHERE lesson_slide_id = ?", (slide_id,))
            connection.execute("DELETE FROM lesson_slides WHERE lesson_version_id = ?", (version_id,))
            connection.execute("DELETE FROM lesson_review_messages WHERE version_id = ?", (version_id,))
            connection.execute("DELETE FROM lesson_versions WHERE id = ?", (version_id,))

    async def update_lesson_version_status(self, version_id: str, status: str) -> None:
        """Update only lifecycle status; content/version identity is immutable."""
        allowed = {"draft", "ready", "in_simulation", "reviewed", "superseded", "final"}
        if status not in allowed:
            raise ValueError(f"invalid lesson version status: {status}")
        await asyncio.to_thread(self._update_lesson_version_status_sync, version_id, status)

    def _update_lesson_version_status_sync(self, version_id: str, status: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE lesson_versions SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now().isoformat(), version_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"lesson version not found: {version_id}")

    async def replace_draft_lesson_version(self, version: LessonVersion) -> LessonVersion:
        """Atomically replace editable Blueprint content before simulation starts."""
        await asyncio.to_thread(self._replace_draft_lesson_version_sync, version)
        return version

    def _replace_draft_lesson_version_sync(self, version: LessonVersion) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT run_id, status FROM lesson_versions WHERE id = ?", (version.id,)
            ).fetchone()
            if row is None or row["run_id"] != version.run_id:
                raise ValueError("lesson version not found in run")
            if row["status"] != "draft":
                raise ValueError("only a draft lesson version can be edited")
            referenced = connection.execute(
                "SELECT 1 FROM simulation_rounds WHERE lesson_version_id = ? LIMIT 1", (version.id,)
            ).fetchone()
            if referenced:
                raise ValueError("lesson version is already used by a simulation round")
            connection.execute("DELETE FROM lesson_slides WHERE lesson_version_id = ?", (version.id,))
            connection.execute(
                """UPDATE lesson_versions
                   SET title = ?, learning_objectives_json = ?, knowledge_points_json = ?,
                       estimated_minutes = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    version.title,
                    _json(version.learning_objectives),
                    _json(version.knowledge_points),
                    version.estimated_minutes,
                    version.updated_at.isoformat(),
                    version.id,
                ),
            )
            for slide in version.slides:
                self._insert_slide(connection, version.id, slide)

    async def append_lesson_review_message(self, item: LessonReviewMessage) -> LessonReviewMessage:
        await asyncio.to_thread(self._append_lesson_review_message_sync, item)
        return item

    def _append_lesson_review_message_sync(self, item: LessonReviewMessage) -> None:
        with self._connect() as connection:
            version = connection.execute(
                "SELECT run_id FROM lesson_versions WHERE id = ?", (item.version_id,)
            ).fetchone()
            if version is None or version["run_id"] != item.run_id:
                raise ValueError("review message crosses run or lesson version boundary")
            connection.execute(
                """INSERT INTO lesson_review_messages
                   (message_id, run_id, version_id, slide_id, role, content, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (item.message_id, item.run_id, item.version_id, item.slide_id, item.role, item.content, item.created_at.isoformat()),
            )

    async def list_lesson_review_messages(self, run_id: str, version_id: str) -> list[LessonReviewMessage]:
        rows = await asyncio.to_thread(self._list_lesson_review_messages_sync, run_id, version_id)
        return [LessonReviewMessage.model_validate(dict(row)) for row in rows]

    def _list_lesson_review_messages_sync(self, run_id: str, version_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                """SELECT * FROM lesson_review_messages
                   WHERE run_id = ? AND version_id = ? ORDER BY created_at, rowid""",
                (run_id, version_id),
            ).fetchall()

    def _list_lesson_versions_sync(self, run_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM lesson_versions WHERE run_id = ? ORDER BY version_number", (run_id,)
            ).fetchall()

    def _insert_slide(self, connection: sqlite3.Connection, version_id: str, slide: LessonSlide) -> None:
        now = slide.updated_at.isoformat() if hasattr(slide, "updated_at") else utc_now().isoformat()
        connection.execute(
            """INSERT INTO lesson_slides
            (id, lesson_version_id, slide_id, slide_order, title, purpose,
                 learning_objectives_json, knowledge_points_json, estimated_minutes,
             ppt_content_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slide.id, version_id, slide.slide_id, slide.order, slide.title, slide.purpose,
                 _json(slide.learning_objectives), _json(slide.knowledge_points), slide.estimated_minutes,
             _json(slide.ppt_content.model_dump(mode="json")), now, now),
        )
        for block in slide.speaker_notes:
            connection.execute(
                """INSERT INTO speaker_note_blocks
                (id, lesson_slide_id, block_id, block_order, block_type, content,
                 estimated_seconds, knowledge_point_ids_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (block.id, slide.id, block.block_id, block.order, block.block_type, block.content,
                 block.estimated_seconds, _json(block.knowledge_point_ids), now, now),
            )
        for anchor in slide.interaction_anchors:
            connection.execute(
                """INSERT INTO interaction_anchors
                (id, lesson_slide_id, interaction_id, anchor_type, objective,
                 planned_question, target_student_level, max_questions, after_block_id,
                 knowledge_point_ids_json, priority, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (anchor.id, slide.id, anchor.interaction_id, anchor.type, anchor.objective,
                 anchor.planned_question, anchor.target_student_level, anchor.max_questions,
                 anchor.after_block_id, _json(anchor.knowledge_point_ids), anchor.priority, _json(anchor.metadata)),
            )
        for misconception in slide.expected_misconceptions:
            connection.execute(
                """INSERT INTO expected_misconceptions
                (id, lesson_slide_id, misconception_id, description, correction_strategy,
                 knowledge_point_id, observable_signals_json, recommended_correction)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), slide.id, misconception.misconception_id,
                 misconception.description, misconception.correction_strategy,
                 misconception.knowledge_point_id, _json(misconception.observable_signals), misconception.recommended_correction),
            )

    def _lesson_from_row(self, row: sqlite3.Row) -> LessonVersion:
        with self._connect() as connection:
            slide_rows = connection.execute(
                "SELECT * FROM lesson_slides WHERE lesson_version_id = ? ORDER BY slide_order", (row["id"],)
            ).fetchall()
            slides: list[LessonSlide] = []
            for slide_row in slide_rows:
                blocks = connection.execute(
                    "SELECT * FROM speaker_note_blocks WHERE lesson_slide_id = ? ORDER BY block_order", (slide_row["id"],)
                ).fetchall()
                anchors = connection.execute(
                    "SELECT * FROM interaction_anchors WHERE lesson_slide_id = ? ORDER BY rowid", (slide_row["id"],)
                ).fetchall()
                misconceptions = connection.execute(
                    "SELECT * FROM expected_misconceptions WHERE lesson_slide_id = ? ORDER BY rowid", (slide_row["id"],)
                ).fetchall()
                slides.append(LessonSlide(
                    id=slide_row["id"], slide_id=slide_row["slide_id"], order=slide_row["slide_order"],
                    title=slide_row["title"], purpose=slide_row["purpose"],
                    learning_objectives=_loads(slide_row["learning_objectives_json"], []),
                    knowledge_points=_loads(slide_row["knowledge_points_json"], []),
                    estimated_minutes=slide_row["estimated_minutes"], ppt_content=_loads(slide_row["ppt_content_json"], {}),
                    speaker_notes=[SpeakerNoteBlock(id=item["id"], block_id=item["block_id"], order=item["block_order"], block_type=item["block_type"], content=item["content"], estimated_seconds=item["estimated_seconds"], knowledge_point_ids=_loads(item["knowledge_point_ids_json"], [])) for item in blocks],
                    interaction_anchors=[{"id": item["id"], "interaction_id": item["interaction_id"], "type": item["anchor_type"], "objective": item["objective"], "planned_question": item["planned_question"], "target_student_level": item["target_student_level"], "max_questions": item["max_questions"], "after_block_id": item["after_block_id"], "knowledge_point_ids": _loads(item["knowledge_point_ids_json"], []), "priority": item["priority"], "metadata": _loads(item["metadata_json"], {})} for item in anchors],
                    expected_misconceptions=[{"misconception_id": item["misconception_id"], "description": item["description"], "correction_strategy": item["correction_strategy"], "knowledge_point_id": item["knowledge_point_id"], "observable_signals": _loads(item["observable_signals_json"], []), "recommended_correction": item["recommended_correction"]} for item in misconceptions],
                ))
        return LessonVersion(
            id=row["id"], lesson_id=row["lesson_id"], run_id=row["run_id"], version_number=row["version_number"],
            source_version_id=row["source_version_id"], created_from_round_id=row["created_from_round_id"],
            title=row["title"], learning_objectives=_loads(row["learning_objectives_json"], []), knowledge_points=_loads(row["knowledge_points_json"], []),
            estimated_minutes=row["estimated_minutes"], status=row["status"], slides=slides,
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    async def create_simulation_round(self, item: SimulationRound) -> SimulationRound:
        await asyncio.to_thread(self._create_round_sync, item)
        return item

    def _create_round_sync(self, item: SimulationRound) -> None:
        with self._connect() as connection:
            self._ensure_run_connection(connection, item.run_id)
            connection.execute(
                """INSERT INTO simulation_rounds
                (id, run_id, round_number, lesson_version_id, scenario_seed, status,
                 current_slide_id, current_slide_index, virtual_elapsed_seconds, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item.id, item.run_id, item.round_number, item.lesson_version_id, item.scenario_seed,
                 item.status, item.current_slide_id, item.current_slide_index, item.virtual_elapsed_seconds,
                 _iso(item.started_at), _iso(item.completed_at)),
            )

    async def get_simulation_round(self, round_id: str) -> SimulationRound | None:
        row = await asyncio.to_thread(self._get_round_sync, round_id)
        return SimulationRound.model_validate(dict(row)) if row else None

    async def list_simulation_rounds(self, run_id: str) -> list[SimulationRound]:
        rows = await asyncio.to_thread(self._list_rounds_sync, run_id)
        return [SimulationRound.model_validate(dict(row)) for row in rows]

    def _list_rounds_sync(self, run_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM simulation_rounds WHERE run_id = ? ORDER BY round_number", (run_id,)).fetchall()

    def _get_round_sync(self, round_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM simulation_rounds WHERE id = ?", (round_id,)).fetchone()

    async def save_classroom_state(self, item: ClassroomState) -> ClassroomState:
        await asyncio.to_thread(self._save_state_sync, item)
        await asyncio.to_thread(self._sync_round_from_state_sync, item)
        return item

    def _sync_round_from_state_sync(self, item: ClassroomState) -> None:
        now = utc_now().isoformat()
        round_status = "running" if item.status == "active" else item.status
        with self._connect() as connection:
            connection.execute(
                """UPDATE simulation_rounds
                   SET status = ?, current_slide_id = ?, current_slide_index = ?,
                       virtual_elapsed_seconds = ?,
                       started_at = COALESCE(started_at, CASE WHEN ? = 'active' THEN ? ELSE started_at END),
                       completed_at = CASE WHEN ? IN ('completed', 'stopped') THEN COALESCE(completed_at, ?) ELSE completed_at END
                   WHERE id = ? AND run_id = ?""",
                (round_status, item.current_slide_id, item.current_slide_index,
                 item.virtual_elapsed_seconds, item.status, now, item.status, now,
                 item.round_id, item.run_id),
            )

    def _save_state_sync(self, item: ClassroomState) -> None:
        now = item.updated_at.isoformat()
        with self._connect() as connection:
            existing = connection.execute("SELECT state_version FROM classroom_states WHERE round_id = ?", (item.round_id,)).fetchone()
            if existing and item.version < int(existing["state_version"]):
                raise ValueError("classroom state version cannot move backwards")
            connection.execute(
                """INSERT INTO classroom_states
                (round_id, run_id, phase, current_slide_id, current_slide_index, current_block_id,
                 active_agent_id, turn_count, followup_depth, slide_interaction_count,
                 student_question_count, virtual_elapsed_seconds, status, state_version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(round_id) DO UPDATE SET run_id=excluded.run_id, phase=excluded.phase,
                 current_slide_id=excluded.current_slide_id, current_slide_index=excluded.current_slide_index,
                 current_block_id=excluded.current_block_id, active_agent_id=excluded.active_agent_id,
                 turn_count=excluded.turn_count, followup_depth=excluded.followup_depth,
                 slide_interaction_count=excluded.slide_interaction_count,
                 student_question_count=excluded.student_question_count,
                 virtual_elapsed_seconds=excluded.virtual_elapsed_seconds, status=excluded.status,
                 state_version=excluded.state_version, updated_at=excluded.updated_at""",
                (item.round_id, item.run_id, item.phase, item.current_slide_id, item.current_slide_index,
                 item.current_block_id, item.active_agent_id, item.turn_count, item.followup_depth,
                 item.slide_interaction_count, item.student_question_count, item.virtual_elapsed_seconds,
                 item.status, item.version, now),
            )

    async def get_classroom_state(self, round_id: str) -> ClassroomState | None:
        row = await asyncio.to_thread(self._get_state_sync, round_id)
        return ClassroomState(
            run_id=row["run_id"], round_id=row["round_id"], phase=row["phase"], current_slide_id=row["current_slide_id"],
            current_slide_index=row["current_slide_index"], current_block_id=row["current_block_id"], active_agent_id=row["active_agent_id"],
            turn_count=row["turn_count"], followup_depth=row["followup_depth"], slide_interaction_count=row["slide_interaction_count"],
            student_question_count=row["student_question_count"], virtual_elapsed_seconds=row["virtual_elapsed_seconds"],
            status=row["status"], version=row["state_version"], updated_at=row["updated_at"],
        ) if row else None

    def _get_state_sync(self, round_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM classroom_states WHERE round_id = ?", (round_id,)).fetchone()

    async def append_classroom_event(self, event: ClassroomEvent) -> ClassroomEvent:
        sequence = await asyncio.to_thread(self._append_event_sync, event)
        return event.model_copy(update={"sequence": sequence})

    def _append_event_sync(self, event: ClassroomEvent) -> int:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT COALESCE(MAX(sequence), 0) AS max_sequence FROM classroom_events WHERE run_id = ?", (event.run_id,)).fetchone()
            expected = int(row["max_sequence"]) + 1
            sequence = event.sequence or expected
            if sequence != expected:
                raise ValueError(f"classroom event sequence must be {expected}, got {sequence}")
            connection.execute(
                """INSERT INTO classroom_events
                (event_id, run_id, round_id, slide_id, sequence, actor_id, actor_role,
                 event_type, content, reply_to, target_agent_id, metadata_json,
                 virtual_timestamp, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event.event_id, event.run_id, event.round_id, event.slide_id, sequence, event.actor_id,
                 event.actor_role, event.event_type.value if hasattr(event.event_type, "value") else event.event_type, event.content, event.reply_to, event.target_agent_id,
                 _json(event.metadata), event.virtual_timestamp, event.created_at.isoformat()),
            )
            return sequence

    async def list_classroom_events(self, run_id: str, round_id: str | None = None, after_sequence: int = 0) -> list[ClassroomEvent]:
        rows = await asyncio.to_thread(self._list_events_sync, run_id, round_id, after_sequence)
        return [ClassroomEvent(event_id=row["event_id"], run_id=row["run_id"], round_id=row["round_id"], slide_id=row["slide_id"], sequence=row["sequence"], actor_id=row["actor_id"], actor_role=row["actor_role"], event_type=row["event_type"], content=row["content"], reply_to=row["reply_to"], target_agent_id=row["target_agent_id"], metadata=_loads(row["metadata_json"], {}), virtual_timestamp=row["virtual_timestamp"], created_at=row["created_at"]) for row in rows]

    def _list_events_sync(self, run_id: str, round_id: str | None, after_sequence: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            if round_id:
                return connection.execute("SELECT * FROM classroom_events WHERE run_id = ? AND round_id = ? AND sequence > ? ORDER BY sequence", (run_id, round_id, after_sequence)).fetchall()
            return connection.execute("SELECT * FROM classroom_events WHERE run_id = ? AND sequence > ? ORDER BY sequence", (run_id, after_sequence)).fetchall()

    async def save_student_persona(self, item: StudentPersona) -> StudentPersona:
        await asyncio.to_thread(self._save_persona_sync, item)
        return item

    def _save_persona_sync(self, item: StudentPersona) -> None:
        with self._connect() as connection:
            self._ensure_run_connection(connection, item.run_id)
            connection.execute("""INSERT INTO student_personas
                (id, run_id, student_id, name, level, ability, prior_knowledge_json, engagement,
                 confidence, verbosity, question_propensity, answer_propensity, misconception_profile_json,
                 scenario_seed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, student_id) DO UPDATE SET id=excluded.id, name=excluded.name,
                 level=excluded.level, ability=excluded.ability, prior_knowledge_json=excluded.prior_knowledge_json,
                 engagement=excluded.engagement, confidence=excluded.confidence, verbosity=excluded.verbosity,
                 question_propensity=excluded.question_propensity, answer_propensity=excluded.answer_propensity,
                 misconception_profile_json=excluded.misconception_profile_json, scenario_seed=excluded.scenario_seed""",
                (item.id, item.run_id, item.student_id, item.name, item.level, item.ability, _json(item.prior_knowledge), item.engagement, item.confidence, item.verbosity, item.question_propensity, item.answer_propensity, _json(item.misconception_profile), item.scenario_seed, item.created_at.isoformat()))

    async def get_student_persona(self, run_id: str, student_id: str) -> StudentPersona | None:
        row = await asyncio.to_thread(self._get_persona_sync, run_id, student_id)
        return _model_from_row(StudentPersona, row, {"prior_knowledge": "prior_knowledge_json", "misconception_profile": "misconception_profile_json"}) if row else None

    async def list_student_personas(self, run_id: str) -> list[StudentPersona]:
        rows = await asyncio.to_thread(self._list_personas_sync, run_id)
        return [_model_from_row(StudentPersona, row, {"prior_knowledge": "prior_knowledge_json", "misconception_profile": "misconception_profile_json"}) for row in rows]

    def _list_personas_sync(self, run_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM student_personas WHERE run_id = ? ORDER BY student_id", (run_id,)).fetchall()

    def _get_persona_sync(self, run_id: str, student_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM student_personas WHERE run_id = ? AND student_id = ?", (run_id, student_id)).fetchone()

    async def save_student_scenario_baseline(self, item: StudentScenarioBaseline) -> StudentScenarioBaseline:
        await asyncio.to_thread(self._save_baseline_sync, item)
        return item

    def _save_baseline_sync(self, item: StudentScenarioBaseline) -> None:
        with self._connect() as connection:
            self._ensure_run_connection(connection, item.run_id)
            connection.execute("""INSERT INTO student_scenario_baselines
                (id, run_id, student_id, initial_mastery_json, initial_confidence_json,
                 initial_misconceptions_json, prior_knowledge_json, scenario_seed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, student_id) DO UPDATE SET id=excluded.id,
                 initial_mastery_json=excluded.initial_mastery_json, initial_confidence_json=excluded.initial_confidence_json,
                 initial_misconceptions_json=excluded.initial_misconceptions_json,
                 prior_knowledge_json=excluded.prior_knowledge_json, scenario_seed=excluded.scenario_seed""",
                (item.id, item.run_id, item.student_id, _json(item.initial_mastery), _json(item.initial_confidence), _json(item.initial_misconceptions), _json(item.prior_knowledge), item.scenario_seed, item.created_at.isoformat()))

    async def get_student_scenario_baseline(self, run_id: str, student_id: str) -> StudentScenarioBaseline | None:
        row = await asyncio.to_thread(self._get_baseline_sync, run_id, student_id)
        return _model_from_row(StudentScenarioBaseline, row, {"initial_mastery": "initial_mastery_json", "initial_confidence": "initial_confidence_json", "initial_misconceptions": "initial_misconceptions_json", "prior_knowledge": "prior_knowledge_json"}) if row else None

    def _get_baseline_sync(self, run_id: str, student_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM student_scenario_baselines WHERE run_id = ? AND student_id = ?", (run_id, student_id)).fetchone()

    async def save_student_cognitive_state(self, item: StudentCognitiveState) -> StudentCognitiveState:
        await asyncio.to_thread(self._save_cognitive_sync, item)
        return item

    async def list_student_cognitive_states(self, round_id: str, student_id: str | None = None) -> list[StudentCognitiveState]:
        rows = await asyncio.to_thread(self._list_cognitive_sync, round_id, student_id)
        return [self._cognitive_from_row(row) for row in rows]

    def _list_cognitive_sync(self, round_id: str, student_id: str | None) -> list[sqlite3.Row]:
        with self._connect() as connection:
            if student_id:
                return connection.execute("SELECT * FROM student_cognitive_states WHERE round_id = ? AND student_id = ? ORDER BY knowledge_point_id", (round_id, student_id)).fetchall()
            return connection.execute("SELECT * FROM student_cognitive_states WHERE round_id = ? ORDER BY student_id, knowledge_point_id", (round_id,)).fetchall()

    @staticmethod
    def _cognitive_from_row(row: sqlite3.Row) -> StudentCognitiveState:
        return StudentCognitiveState(id=row["id"], round_id=row["round_id"], student_id=row["student_id"], knowledge_point_id=row["knowledge_point_id"], current_mastery=row["current_mastery"], current_confidence=row["current_confidence"], misconceptions=_loads(row["misconceptions_json"], []), resolved_misconceptions=_loads(row["resolved_misconceptions_json"], []), engagement_runtime=row["engagement_runtime"], last_event_id=row["last_event_id"], updated_at=row["updated_at"])

    def _save_cognitive_sync(self, item: StudentCognitiveState) -> None:
        with self._connect() as connection:
            connection.execute("""INSERT INTO student_cognitive_states
                (id, round_id, student_id, knowledge_point_id, current_mastery, current_confidence,
                 misconceptions_json, resolved_misconceptions_json, engagement_runtime, last_event_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(round_id, student_id, knowledge_point_id) DO UPDATE SET id=excluded.id,
                 current_mastery=excluded.current_mastery, current_confidence=excluded.current_confidence,
                 misconceptions_json=excluded.misconceptions_json, resolved_misconceptions_json=excluded.resolved_misconceptions_json,
                 engagement_runtime=excluded.engagement_runtime, last_event_id=excluded.last_event_id, updated_at=excluded.updated_at""",
                (item.id, item.round_id, item.student_id, item.knowledge_point_id, item.current_mastery, item.current_confidence, _json(item.misconceptions), _json(item.resolved_misconceptions), item.engagement_runtime, item.last_event_id, item.updated_at.isoformat()))

    async def get_student_cognitive_state(self, round_id: str, student_id: str, knowledge_point_id: str) -> StudentCognitiveState | None:
        row = await asyncio.to_thread(self._get_cognitive_sync, round_id, student_id, knowledge_point_id)
        return _model_from_row(StudentCognitiveState, row, {"misconceptions": "misconceptions_json", "resolved_misconceptions": "resolved_misconceptions_json"}) if row else None

    def _get_cognitive_sync(self, round_id: str, student_id: str, knowledge_point_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM student_cognitive_states WHERE round_id = ? AND student_id = ? AND knowledge_point_id = ?", (round_id, student_id, knowledge_point_id)).fetchone()

    async def save_agent_instance(self, item: ClassroomAgentInstance) -> ClassroomAgentInstance:
        await asyncio.to_thread(self._save_agent_sync, item)
        return item

    async def get_agent_instance(self, run_id: str, agent_key: str) -> ClassroomAgentInstance | None:
        row = await asyncio.to_thread(self._get_agent_sync, run_id, agent_key)
        if not row:
            return None
        return ClassroomAgentInstance(
            id=row["id"], run_id=row["run_id"], agent_key=row["agent_key"], role=row["role"],
            display_name=row["display_name"], student_id=row["student_id"], persona_id=row["persona_id"],
            status=row["status"], config=_loads(row["config_json"], {}), created_at=row["created_at"],
        )

    def _get_agent_sync(self, run_id: str, agent_key: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM classroom_agent_instances WHERE run_id = ? AND agent_key = ?", (run_id, agent_key)).fetchone()

    def _save_agent_sync(self, item: ClassroomAgentInstance) -> None:
        with self._connect() as connection:
            self._ensure_run_connection(connection, item.run_id)
            connection.execute("""INSERT INTO classroom_agent_instances
                (id, run_id, agent_key, role, display_name, student_id, persona_id, status, config_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, agent_key) DO UPDATE SET id=excluded.id, role=excluded.role,
                 display_name=excluded.display_name, student_id=excluded.student_id, persona_id=excluded.persona_id,
                 status=excluded.status, config_json=excluded.config_json""",
                (item.id, item.run_id, item.agent_key, item.role, item.display_name, item.student_id, item.persona_id, item.status, _json(item.config), item.created_at.isoformat()))

    async def save_teacher_directive(self, item: TeacherDirective) -> TeacherDirective:
        await asyncio.to_thread(self._save_directive_sync, item)
        return item

    def _save_directive_sync(self, item: TeacherDirective) -> None:
        with self._connect() as connection:
            self._ensure_run_connection(connection, item.run_id)
            connection.execute(
                """INSERT INTO teacher_directives
                (directive_id, run_id, round_id, slide_id, source_event_id, content, intent, scope, status, created_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(directive_id) DO UPDATE SET status=excluded.status, resolved_at=excluded.resolved_at""",
                (item.directive_id, item.run_id, item.round_id, item.slide_id, item.source_event_id, item.content,
                 item.intent, item.scope, item.status, item.created_at.isoformat(), _iso(item.resolved_at)),
            )

    async def get_teacher_directive(self, directive_id: str) -> TeacherDirective | None:
        row = await asyncio.to_thread(self._get_directive_sync, directive_id)
        return _model_from_row(TeacherDirective, row, {}) if row else None

    def _get_directive_sync(self, directive_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM teacher_directives WHERE directive_id = ?", (directive_id,)
            ).fetchone()

    async def list_teacher_directives(
        self, run_id: str, *, round_id: str | None = None, status: str | None = None
    ) -> list[TeacherDirective]:
        rows = await asyncio.to_thread(self._list_directives_sync, run_id, round_id, status)
        return [_model_from_row(TeacherDirective, row, {}) for row in rows]

    def _list_directives_sync(self, run_id: str, round_id: str | None, status: str | None) -> list[sqlite3.Row]:
        query = "SELECT * FROM teacher_directives WHERE run_id = ?"
        params: list[Any] = [run_id]
        if round_id:
            query += " AND round_id = ?"
            params.append(round_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at"
        with self._connect() as connection:
            return connection.execute(query, tuple(params)).fetchall()

    async def resolve_teacher_directives(
        self, run_id: str, *, round_id: str | None = None, scope: str | None = None
    ) -> int:
        """把生效中的指令标记为已落实(离开该页/本轮结束/定稿时调用)。"""
        return await asyncio.to_thread(self._resolve_directives_sync, run_id, round_id, scope)

    def _resolve_directives_sync(self, run_id: str, round_id: str | None, scope: str | None) -> int:
        query = "UPDATE teacher_directives SET status = 'resolved', resolved_at = ? WHERE run_id = ? AND status = 'active'"
        params: list[Any] = [utc_now().isoformat(), run_id]
        if round_id:
            query += " AND round_id = ?"
            params.append(round_id)
        if scope:
            query += " AND scope = ?"
            params.append(scope)
        with self._connect() as connection:
            cursor = connection.execute(query, tuple(params))
            return cursor.rowcount

    async def save_supervisor_observation(self, item: SupervisorObservation) -> SupervisorObservation:
        await asyncio.to_thread(self._save_observation_sync, item)
        return item

    def _save_observation_sync(self, item: SupervisorObservation) -> None:
        with self._connect() as connection:
            connection.execute("""INSERT INTO supervisor_observations
                (observation_id, round_id, slide_id, event_ids_json, category, severity, issue, evidence, recommendation, analysis_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_id) DO UPDATE SET event_ids_json=excluded.event_ids_json,
                  category=excluded.category, severity=excluded.severity, issue=excluded.issue,
                  evidence=excluded.evidence, recommendation=excluded.recommendation,
                  analysis_json=excluded.analysis_json""",
                (item.observation_id, item.round_id, item.slide_id, _json(item.event_ids), item.category, item.severity, item.issue, item.evidence, item.recommendation, _json(item.analysis), item.created_at.isoformat()))

    async def list_supervisor_observations(self, round_id: str, slide_id: str | None = None) -> list[SupervisorObservation]:
        rows = await asyncio.to_thread(self._list_observations_sync, round_id, slide_id)
        return [_model_from_row(SupervisorObservation, row, {"event_ids": "event_ids_json", "analysis": "analysis_json"}) for row in rows]

    def _list_observations_sync(self, round_id: str, slide_id: str | None) -> list[sqlite3.Row]:
        with self._connect() as connection:
            if slide_id:
                return connection.execute("SELECT * FROM supervisor_observations WHERE round_id = ? AND slide_id = ? ORDER BY created_at", (round_id, slide_id)).fetchall()
            return connection.execute("SELECT * FROM supervisor_observations WHERE round_id = ? ORDER BY created_at", (round_id,)).fetchall()

    async def save_supervisor_report(self, item: SupervisorReport) -> SupervisorReport:
        await asyncio.to_thread(self._save_report_sync, item)
        return item

    def _save_report_sync(self, item: SupervisorReport) -> None:
        with self._connect() as connection:
            self._ensure_run_connection(connection, item.run_id)
            connection.execute("""INSERT INTO supervisor_reports
                (id, run_id, round_id, overall_score, dimension_scores_json, strengths_json,
                 critical_issues_json, observations_json, revision_priorities_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(round_id) DO UPDATE SET id=excluded.id, overall_score=excluded.overall_score,
                 dimension_scores_json=excluded.dimension_scores_json, strengths_json=excluded.strengths_json,
                 critical_issues_json=excluded.critical_issues_json, observations_json=excluded.observations_json,
                 revision_priorities_json=excluded.revision_priorities_json""",
                (item.id, item.run_id, item.round_id, item.overall_score, _json(item.dimension_scores), _json(item.strengths), _json(item.critical_issues), _json(item.observations), _json(item.revision_priorities), item.created_at.isoformat()))

    async def get_supervisor_report(self, round_id: str) -> SupervisorReport | None:
        row = await asyncio.to_thread(self._get_report_sync, round_id)
        return _model_from_row(SupervisorReport, row, {"dimension_scores": "dimension_scores_json", "strengths": "strengths_json", "critical_issues": "critical_issues_json", "observations": "observations_json", "revision_priorities": "revision_priorities_json"}) if row else None

    def _get_report_sync(self, round_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM supervisor_reports WHERE round_id = ?", (round_id,)).fetchone()

    async def save_revision_patch(self, item: RevisionPatch) -> RevisionPatch:
        await asyncio.to_thread(self._save_patch_sync, item)
        return item

    def _save_patch_sync(self, item: RevisionPatch) -> None:
        with self._connect() as connection:
            self._ensure_run_connection(connection, item.run_id)
            connection.execute("""INSERT INTO revision_patches
                (patch_id, run_id, source_version_id, target_version_id, source_round_id, target_type,
                 slide_id, block_id, field_path, before_json, after_json, reason,
                 source_observation_ids_json, source_intervention_ids_json, status, created_at, applied_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(patch_id) DO UPDATE SET target_version_id=excluded.target_version_id,
                 status=excluded.status, applied_at=excluded.applied_at""",
                (item.patch_id, item.run_id, item.source_version_id, item.target_version_id, item.source_round_id, item.target_type, item.slide_id, item.block_id, item.field_path, _json(item.before), _json(item.after), item.reason, _json(item.source_observation_ids), _json(item.source_intervention_ids), item.status, item.created_at.isoformat(), _iso(item.applied_at)))

    async def list_revision_patches(self, run_id: str, source_round_id: str | None = None) -> list[RevisionPatch]:
        rows = await asyncio.to_thread(self._list_patches_sync, run_id, source_round_id)
        return [_model_from_row(RevisionPatch, row, {"before": "before_json", "after": "after_json", "source_observation_ids": "source_observation_ids_json", "source_intervention_ids": "source_intervention_ids_json"}) for row in rows]

    def _list_patches_sync(self, run_id: str, source_round_id: str | None) -> list[sqlite3.Row]:
        with self._connect() as connection:
            if source_round_id:
                return connection.execute("SELECT * FROM revision_patches WHERE run_id = ? AND source_round_id = ? ORDER BY created_at", (run_id, source_round_id)).fetchall()
            return connection.execute("SELECT * FROM revision_patches WHERE run_id = ? ORDER BY created_at", (run_id,)).fetchall()

    @staticmethod
    def _ensure_run_connection(connection: sqlite3.Connection, run_id: str) -> None:
        now = utc_now().isoformat()
        connection.execute("INSERT OR IGNORE INTO classroom_runs(run_id, workflow_version, created_at, updated_at) VALUES (?, 'classroom_v2', ?, ?)", (run_id, now, now))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _model_from_row(model: type[T], row: sqlite3.Row, mappings: dict[str, str]) -> T:
    data = dict(row)
    for field, column in mappings.items():
        data[field] = _loads(data.pop(column), {} if field in {"before", "after", "analysis", "dimension_scores", "prior_knowledge", "misconception_profile", "initial_mastery", "initial_confidence", "initial_misconceptions"} else [])
    return model.model_validate(data)
