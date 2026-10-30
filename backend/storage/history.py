from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .db import Database
from .settings import SettingsStore


class HistoryStore:
    MAX_REQUEST = 1000
    MAX_SUMMARY = 20_000
    PREVIEW = 300

    def __init__(self, db: Database, settings: SettingsStore, max_rows: int = 1000):
        self.db, self.settings, self.max_rows = db, settings, max_rows

    def record(self, *, request: str, kind: str, status: str, summary: str,
               plan_id: str = "", journal: str | None = None, changed: bool = False) -> str | None:
        """Save one entry. Returns None on success (or when history is off), or a message
        describing the problem. It never raises: history must not break real work."""
        try:
            if not self.settings.get("history_enabled"):
                return None
            with self.db.connection() as conn:
                conn.execute(
                    "INSERT INTO history(created_at, request, kind, status, summary, plan_id, "
                    "journal, changed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     request.replace("\x00", "")[: self.MAX_REQUEST], kind, status,
                     summary.replace("\x00", "")[: self.MAX_SUMMARY], plan_id or "",
                     journal, 1 if changed else 0))
                conn.execute(                      # keep only the newest `max_rows`
                    "DELETE FROM history WHERE id <= "
                    "(SELECT id FROM history ORDER BY id DESC LIMIT 1 OFFSET ?)",
                    (self.max_rows,))
        except sqlite3.Error as exc:
            return f"I couldn't save this to your history ({exc})."
        return None

    def recent(self, limit: int = 50, before_id: int | None = None):
        """Newest first. Returns (items, next_before); pass next_before to get the next page."""
        sql = ("SELECT id, created_at, request, kind, status, "
               "substr(summary, 1, ?) AS preview, changed FROM history")
        params: list = [self.PREVIEW]
        if before_id is not None:
            sql += " WHERE id < ?"
            params.append(before_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.db.connection() as conn:
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        for row in rows:
            row["changed"] = bool(row["changed"])
        return rows, (rows[-1]["id"] if len(rows) == limit else None)

    def get(self, item_id: int) -> dict | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT id, created_at, request, kind, status, summary, plan_id, journal, "
                "changed FROM history WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["changed"] = bool(out["changed"])
        return out

    def clear(self) -> int:
        with self.db.connection() as conn:
            deleted = conn.execute("DELETE FROM history").rowcount
        try:                                       # release the freed pages back to the disk
            with self.db.connection() as conn:
                conn.execute("VACUUM")
        except sqlite3.Error:
            pass
        return deleted