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
