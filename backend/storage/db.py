from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

_V1 = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    request TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    plan_id TEXT,
    journal TEXT,
    changed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _looks_corrupt(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(s in text for s in ("not a database", "malformed", "disk image"))


class Database:
    """A small SQLite file. Every operation opens its own short-lived connection, so it is
    safe to use from the several threads the web server runs requests on."""

    quarantined: Path | None = None

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._init()
        except sqlite3.DatabaseError as exc:
            if not _looks_corrupt(exc):
                raise                      # locked, newer version, etc.: never touch the file
            self.quarantined = self._quarantine()
            self._init()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:                     # commit on success, roll back on error
                yield conn
        finally:
            conn.close()

    def _init(self) -> None:
        with self.connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise sqlite3.DatabaseError(
                    f"This database comes from a newer version of Smart Manager "
                    f"(schema {version}).")
            if version < 1:
                conn.executescript(_V1)    # idempotent, so a crash halfway is harmless
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _quarantine(self) -> Path:
        """Set a damaged file aside (never delete it) and start fresh."""
        aside = self.path.with_name(f"{self.path.name}.corrupt-{time.strftime('%Y%m%d%H%M%S')}")
        self.path.rename(aside)
        return aside