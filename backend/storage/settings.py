from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .db import Database


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    description: str
    default: bool


SPECS: dict[str, Spec] = {s.key: s for s in (
    Spec("history_enabled", "Save request history",
         "Keeps a list of your requests and what happened, on this computer only. "
         "Turning this off keeps the existing history until you clear it.", True),
)}


class SettingsStore:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str) -> bool:
        spec = SPECS[key]                  # KeyError for an unknown setting
        try:
            with self.db.connection() as conn:
                row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        except sqlite3.Error:
            return spec.default
        if row is None or row["value"] not in ("0", "1"):
            return spec.default
        return row["value"] == "1"

    def set(self, key: str, value: bool) -> None:
        if key not in SPECS:
            raise KeyError(key)
        if not isinstance(value, bool):
            raise TypeError("A setting must be true or false.")
        with self.db.connection() as conn:
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
                         (key, "1" if value else "0"))

    def describe(self) -> list[dict]:
        return [{"key": s.key, "label": s.label, "description": s.description,
                 "type": "bool", "value": self.get(s.key)} for s in SPECS.values()]