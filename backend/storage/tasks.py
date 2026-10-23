"""Durable task state and append-only workflow events."""

import json
import sqlite3
from typing import Any, Dict, List, Optional

from storage.database import connect_db


class TaskRepository:
    TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted"}

    @classmethod
    def create(cls, task_id: str, conversation_id: str, goal: str) -> None:
        with connect_db() as conn:
            conn.execute(
                "INSERT INTO tasks (id, conversation_id, goal, status) VALUES (?, ?, ?, 'queued')",
                (task_id, conversation_id, goal),
            )
            cls._append(conn, task_id, "task_queued", {"conversation_id": conversation_id})

    @classmethod
    def transition(
        cls,
        task_id: str,
        status: str,
        *,
        provider: Optional[str] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
        event_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        with connect_db() as conn:
            conn.execute(
                """UPDATE tasks SET status = ?, provider = COALESCE(?, provider),
                   result = COALESCE(?, result), error = COALESCE(?, error),
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (status, provider, result, error, task_id),
            )
            cls._append(conn, task_id, f"task_{status}", event_payload or {})

    @classmethod
    def record_action(cls, task_id: str, observation: Dict[str, Any]) -> None:
        safe = {key: observation.get(key) for key in ("tool", "success", "verified", "error", "duration_ms")}
        cls._event(task_id, "action_observed", safe)

    @classmethod
    def get(cls, task_id: str) -> Optional[Dict[str, Any]]:
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None

    @classmethod
    def events(cls, task_id: str) -> List[Dict[str, Any]]:
        with connect_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, event_type, payload, created_at FROM task_events WHERE task_id = ? ORDER BY id", (task_id,)
            ).fetchall()
            return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    @classmethod
    def reconcile_interrupted(cls) -> int:
        """Mark volatile in-process work as interrupted after an application restart."""
        with connect_db() as conn:
            rows = conn.execute(
                "SELECT id FROM tasks WHERE status IN ('queued', 'planning', 'executing', 'verifying', 'awaiting_approval')"
            ).fetchall()
            for (task_id,) in rows:
                conn.execute("UPDATE tasks SET status = 'interrupted', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
                cls._append(conn, task_id, "task_interrupted", {"reason": "backend_restart"})
            return len(rows)

    @classmethod
    def _event(cls, task_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        with connect_db() as conn:
            cls._append(conn, task_id, event_type, payload)

    @staticmethod
    def _append(conn: sqlite3.Connection, task_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO task_events (task_id, event_type, payload) VALUES (?, ?, ?)",
            (task_id, event_type, json.dumps(payload, default=str)),
        )
