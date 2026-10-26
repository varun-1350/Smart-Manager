import sqlite3
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from storage.database import get_db_path


class HistoryRepository:
    @staticmethod
    def create_or_update_conversation(conv_id: str, title: str) -> None:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversations (id, title, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    updated_at = CURRENT_TIMESTAMP
            """, (conv_id, title))
            conn.commit()

    @staticmethod
    def list_conversations() -> List[Dict[str, Any]]:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def save_message(
        msg_id: str,
        conversation_id: str,
        role: str,
        content: str,
        status: str = "completed",
    ) -> None:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO messages (id, conversation_id, role, content, status)
                VALUES (?, ?, ?, ?, ?)
            """, (msg_id, conversation_id, role, content, status))
            conn.commit()

    @staticmethod
    def get_messages(conversation_id: str) -> List[Dict[str, Any]]:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, conversation_id, role, content, status, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
            """, (conversation_id,))
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def log_action(
        task_id: str,
        conversation_id: str,
        tool: str,
        parameters: Dict[str, Any],
        success: bool,
        result: Any = None,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
        verified: bool = False,
    ) -> None:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO action_logs (
                    task_id, conversation_id, tool, parameters,
                    success, result, error, duration_ms, verified
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id,
                conversation_id,
                tool,
                json.dumps(parameters),
                1 if success else 0,
                json.dumps(result) if result is not None else None,
                error,
                duration_ms,
                1 if verified else 0,
            ))
            conn.commit()

    @staticmethod
    def delete_conversation(conversation_id: str) -> bool:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            cursor.execute("DELETE FROM action_logs WHERE conversation_id = ?", (conversation_id,))
            cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def clear_all_conversations() -> None:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages")
            cursor.execute("DELETE FROM action_logs")
            cursor.execute("DELETE FROM conversations")
            conn.commit()


class OperationHistoryRepository:
    """Manages file operation history and undo state for batch file actions."""

    @staticmethod
    def record_operation(
        batch_id: str,
        operation_type: str,
        source_path: str,
        destination_path: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        from uuid import uuid4
        op_id = f"op-{uuid4()}"
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO operation_history (id, batch_id, operation_type, source_path, destination_path, extra_data, undone)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (
                op_id,
                batch_id,
                operation_type,
                source_path,
                destination_path,
                json.dumps(extra_data or {}),
            ))
            conn.commit()
            return op_id

    @staticmethod
    def get_last_undoable_batch() -> Optional[Dict[str, Any]]:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT batch_id, created_at, COUNT(*) as op_count
                FROM operation_history
                WHERE undone = 0 AND operation_type IN ('move', 'rename', 'trash', 'copy')
                GROUP BY batch_id
                ORDER BY MAX(created_at) DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if not row:
                return None
            batch_id = row["batch_id"]
            cursor.execute("""
                SELECT id, batch_id, operation_type, source_path, destination_path, extra_data, created_at
                FROM operation_history
                WHERE batch_id = ?
                ORDER BY id DESC
            """, (batch_id,))
            ops = [
                {**dict(r), "extra_data": json.loads(r["extra_data"])}
                for r in cursor.fetchall()
            ]
            return {
                "batch_id": batch_id,
                "created_at": row["created_at"],
                "operations": ops,
            }

    @staticmethod
    def mark_batch_undone(batch_id: str) -> None:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE operation_history SET undone = 1 WHERE batch_id = ?", (batch_id,))
            conn.commit()

    @staticmethod
    def list_recent_batches(limit: int = 15) -> List[Dict[str, Any]]:
        path = get_db_path()
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT batch_id, MAX(created_at) as created_at, MIN(undone) as is_active, COUNT(*) as op_count
                FROM operation_history
                GROUP BY batch_id
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            batches = []
            for b in cursor.fetchall():
                cursor.execute("""
                    SELECT id, operation_type, source_path, destination_path, extra_data
                    FROM operation_history
                    WHERE batch_id = ?
                """, (b["batch_id"],))
                ops = [
                    {**dict(r), "extra_data": json.loads(r["extra_data"])}
                    for r in cursor.fetchall()
                ]
                batches.append({
                    "batch_id": b["batch_id"],
                    "created_at": b["created_at"],
                    "undone": b["is_active"] == 1,
                    "op_count": b["op_count"],
                    "operations": ops,
                })
            return batches

