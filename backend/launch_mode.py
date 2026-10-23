"""Print the effective inference mode without importing the desktop application."""

import json
import sqlite3
from pathlib import Path


def get_launch_mode() -> str:
    db_path = Path(__file__).resolve().parent.parent / "data" / "smart_manager.db"
    if not db_path.exists():
        return "local"
    try:
        with sqlite3.connect(db_path) as conn:
            rows = dict(conn.execute("SELECT key, value FROM app_settings"))
        mode = rows.get("ai_provider_mode", "local").lower()
        if mode == "online":
            return "online"
        active_model = rows.get("active_model_id", "")
        configured = json.loads(rows.get("configured_online_models", "[]"))
        if any(model.get("id") == active_model for model in configured if isinstance(model, dict)):
            return "online"
        return "auto" if mode == "auto" else "local"
    except (sqlite3.Error, ValueError, TypeError):
        # Local remains the safe default for a missing or unreadable preference.
        return "local"


if __name__ == "__main__":
    print(get_launch_mode())
