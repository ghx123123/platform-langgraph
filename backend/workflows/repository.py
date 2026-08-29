import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.workflows.models import RunEvent, RunRecord, TeacherDraftVersion, utc_now


class WorkflowRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )"""
            )
            migration_dir = Path(__file__).resolve().parents[1] / "migrations"
            for migration in sorted(migration_dir.glob("*.sql")):
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?", (migration.name,)
                ).fetchone()
                if applied:
                    continue
                connection.executescript(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (migration.name, utc_now().isoformat()),
                )

    async def create_run(self, run: RunRecord) -> RunRecord:
        await asyncio.to_thread(self._create_run_sync, run)
        return run

    def _create_run_sync(self, run: RunRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO workflow_runs
                (id, thread_id, template_id, objective, context, status, provider,
                 current_node, final_output, review_json, teaching_data_json, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.id,
                    run.thread_id,
                    run.template_id,
                    run.objective,
                    run.context,
                    run.status,
                    run.provider,
                    run.current_node,
                    run.final_output,
                    json.dumps(run.review, ensure_ascii=False) if run.review else None,
                    json.dumps(run.teaching_data, ensure_ascii=False),
                    run.error,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                ),
            )

    async def update_run(self, run_id: str, **changes: Any) -> RunRecord | None:
        changes["updated_at"] = utc_now().isoformat()
        await asyncio.to_thread(self._update_run_sync, run_id, changes)
        return await self.get_run(run_id)

    def _update_run_sync(self, run_id: str, changes: dict[str, Any]) -> None:
        allowed = {"status", "current_node", "final_output", "review_json", "teaching_data_json", "pending_input_json", "context", "thread_id", "error", "updated_at"}
        json_columns = {"review_json", "teaching_data_json", "pending_input_json"}
        normalized: dict[str, Any] = {}
        for key, value in changes.items():
            db_key = {"review": "review_json", "teaching_data": "teaching_data_json", "pending_input": "pending_input_json"}.get(key, key)
            if db_key not in allowed:
                continue
            # None 表示清除该字段（如恢复运行时清掉暂停态），需要原样写入
            normalized[db_key] = json.dumps(value, ensure_ascii=False) if db_key in json_columns and value is not None else value
        if not normalized:
            return
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE workflow_runs SET {assignments} WHERE id = ?",
                [*normalized.values(), run_id],
            )

    async def get_run(self, run_id: str) -> RunRecord | None:
        row = await asyncio.to_thread(self._get_run_sync, run_id)
        return self._row_to_run(row) if row else None

    def _get_run_sync(self, run_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()

    async def list_runs(self, limit: int = 50) -> list[RunRecord]:
        rows = await asyncio.to_thread(self._list_runs_sync, limit)
        return [self._row_to_run(row) for row in rows]

    def _list_runs_sync(self, limit: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM workflow_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()

    async def delete_run(self, run_id: str) -> bool:
        return await asyncio.to_thread(self._delete_run_sync, run_id)

    def _delete_run_sync(self, run_id: str) -> bool:
        # workflow_events 通过 ON DELETE CASCADE 一并清除（_connect 已开启 foreign_keys）
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM workflow_runs WHERE id = ?", (run_id,))
            return cursor.rowcount > 0

    async def get_teacher_draft(self, run_id: str) -> TeacherDraftVersion | None:
        row = await asyncio.to_thread(self._get_teacher_draft_sync, run_id)
        return self._row_to_teacher_draft(row) if row else None

    def _get_teacher_draft_sync(self, run_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                """SELECT version, content, status, created_at
                   FROM teacher_draft_versions
                   WHERE run_id = ?
                   ORDER BY version DESC LIMIT 1""",
                (run_id,),
            ).fetchone()

    async def list_teacher_draft_versions(self, run_id: str, limit: int = 20) -> list[TeacherDraftVersion]:
        rows = await asyncio.to_thread(self._list_teacher_draft_versions_sync, run_id, limit)
        return [self._row_to_teacher_draft(row) for row in rows]

    def _list_teacher_draft_versions_sync(self, run_id: str, limit: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                """SELECT version, content, status, created_at
                   FROM teacher_draft_versions
                   WHERE run_id = ?
                   ORDER BY version DESC LIMIT ?""",
                (run_id, limit),
            ).fetchall()

    async def save_teacher_draft(
        self,
        run_id: str,
        content: str,
        status: str,
        base_version: int,
    ) -> TeacherDraftVersion | None:
        row = await asyncio.to_thread(
            self._save_teacher_draft_sync, run_id, content, status, base_version
        )
        return self._row_to_teacher_draft(row) if row else None

    def _save_teacher_draft_sync(
        self,
        run_id: str,
        content: str,
        status: str,
        base_version: int,
    ) -> sqlite3.Row | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                """SELECT version, content, status, created_at
                   FROM teacher_draft_versions
                   WHERE run_id = ? ORDER BY version DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            current_version = int(latest["version"]) if latest else 0
            if current_version != base_version:
                connection.rollback()
                return None
            if latest and latest["content"] == content and latest["status"] == status:
                return latest
            next_version = current_version + 1
            created_at = utc_now().isoformat()
            connection.execute(
                """INSERT INTO teacher_draft_versions
                   (run_id, version, content, status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, next_version, content, status, created_at),
            )
            return connection.execute(
                """SELECT version, content, status, created_at
                   FROM teacher_draft_versions
                   WHERE run_id = ? AND version = ?""",
                (run_id, next_version),
            ).fetchone()

    async def append_event(self, event: RunEvent) -> RunEvent:
        sequence = await asyncio.to_thread(self._append_event_sync, event)
        return event.model_copy(update={"sequence": sequence})

    def _append_event_sync(self, event: RunEvent) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO workflow_events
                (run_id, event_type, node, message, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.run_id,
                    event.event_type,
                    event.node,
                    event.message,
                    json.dumps(event.payload, ensure_ascii=False),
                    event.created_at.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    async def list_events(self, run_id: str, after: int = 0) -> list[RunEvent]:
        rows = await asyncio.to_thread(self._list_events_sync, run_id, after)
        return [
            RunEvent(
                sequence=row["sequence"],
                run_id=row["run_id"],
                event_type=row["event_type"],
                node=row["node"],
                message=row["message"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def _list_events_sync(self, run_id: str, after: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM workflow_events WHERE run_id = ? AND sequence > ? ORDER BY sequence",
                (run_id, after),
            ).fetchall()

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            thread_id=row["thread_id"],
            template_id=row["template_id"],
            objective=row["objective"],
            context=row["context"],
            status=row["status"],
            provider=row["provider"],
            current_node=row["current_node"],
            final_output=row["final_output"],
            review=json.loads(row["review_json"]) if row["review_json"] else None,
            teaching_data=json.loads(row["teaching_data_json"]) if "teaching_data_json" in row.keys() and row["teaching_data_json"] else {},
            pending_input=json.loads(row["pending_input_json"]) if "pending_input_json" in row.keys() and row["pending_input_json"] else None,
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_teacher_draft(row: sqlite3.Row) -> TeacherDraftVersion:
        return TeacherDraftVersion(
            version=row["version"],
            content=row["content"],
            status=row["status"],
            created_at=row["created_at"],
        )
