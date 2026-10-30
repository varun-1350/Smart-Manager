from __future__ import annotations
import sqlite3
import argparse
import secrets
from pathlib import Path

import uvicorn

from backend.api.app import create_app
from backend.nlp.intent_classifier import IntentClassifier, ModelNotTrainedError
from backend.security.config import load_config, sandbox_config
from backend.security.errors import SecurityError
from backend.security.paths import PathPolicy
from backend.services.assistant import Assistant
from backend.storage.db import Database
from backend.storage.history import HistoryStore
from backend.storage.settings import SettingsStore
from backend.storage.db import Database
from backend.storage.history import HistoryStore
from backend.storage.settings import SettingsStore

PROJECT = Path(__file__).resolve().parents[1]
class StartupError(Exception):
    """Something needed at startup couldn't be set up. The message is safe to print."""

def build_assistant(sandbox, allow_real_folders):
    """Raises SecurityError or ModelNotTrainedError with a message that is safe to print."""
    if not sandbox and not allow_real_folders:
        raise SecurityError("Refusing to start on your real folders. "
                            "Use --sandbox FOLDER, or add --allow-real-folders.")
    classifier = IntentClassifier.load()
    cfg = sandbox_config(sandbox) if sandbox else load_config()
    try:
        db = Database(PROJECT / "data" / "smartmanager.db")
    except (sqlite3.Error, OSError) as exc:
        raise StartupError(f"Couldn't open the history database: {exc}") from exc
    if db.quarantined:
        print(f"The old history file was damaged, so I set it aside as "
              f"{db.quarantined.name} and started a new one.")
    history = HistoryStore(db, SettingsStore(db))
    assistant = Assistant(classifier, PathPolicy(cfg),
                          journal_dir=PROJECT / "data" / "journal",
                          backup_dir=PROJECT / "data" / "backups", history=history)
    return assistant, cfg


def main() -> int:
    ap = argparse.ArgumentParser(description="Smart Manager local API")
    ap.add_argument("--sandbox", help="Allow ONLY this folder (recommended for testing).")
    ap.add_argument("--allow-real-folders", action="store_true",
                    help="Required to run on your real folders when no sandbox is given.")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    try:
        assistant, cfg = build_assistant(args.sandbox, args.allow_real_folders)
    except (ModelNotTrainedError, SecurityError, StartupError) as exc:
        print(exc)
        return 1

    token = secrets.token_urlsafe(32)               # new every launch
    app = create_app(assistant, token)
    print("Allowed folders:\n  " + "\n  ".join(str(p) for p in cfg.allowed_roots))
    print(f"\nListening on http://127.0.0.1:{args.port}  (this machine only)")
    print(f"Session token (development only): {token}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")   # host is fixed
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

def make_history(env):
    db = Database(env.base / "app.db")
    settings = SettingsStore(db)
    return HistoryStore(db, settings), settings


def test_history_records_what_happened(env):
    history, _ = make_history(env)
    a = make_assistant(env, history=history)
    a.handle("")                                   # a blank request isn't recorded
    a.handle("What is the weather")
    a.handle("Open setup.exe")
    turn = a.handle(TEXT)
    assert history.recent(10)[0][0]["request"] == "Open setup.exe"    # approval isn't logged yet
    a.approve(turn.turn_id, turn.digest)
    items, _ = history.recent(20)
    assert [(i["request"], i["kind"], i["status"]) for i in reversed(items)] == [
        ("What is the weather", "unsupported", "unsupported"),
        ("Open setup.exe", "blocked", "blocked"),
        (TEXT, "executed", "completed")]
    assert items[0]["changed"] is True


def test_a_rejected_request_is_recorded(env):
    history, _ = make_history(env)
    a = make_assistant(env, history=history)
    turn = a.handle(TEXT)
    a.reject(turn.turn_id)
    item = history.recent(5)[0][0]
    assert (item["request"], item["status"], item["changed"]) == (TEXT, "rejected", False)


def test_read_only_runs_are_recorded_as_not_changed(env):
    history, _ = make_history(env)
    a = make_assistant(env, history=history)
    a.handle("Find PDFs in Downloads")
    item = history.recent(5)[0][0]
    assert item["status"] == "completed" and item["changed"] is False


def test_history_off_records_nothing_but_work_continues(env):
    history, settings = make_history(env)
    settings.set("history_enabled", False)
    a = make_assistant(env, history=history)
    assert a.handle("Find PDFs in Downloads").kind == "executed"
    assert history.recent(5) == ([], None)


def test_a_history_failure_never_blocks_the_work(env, monkeypatch):
    history, _ = make_history(env)
    monkeypatch.setattr(history, "record",
                        lambda **kw: "I couldn't save this to your history (disk full).")
    a = make_assistant(env, history=history)
    turn = a.handle("Find PDFs in Downloads")
    assert turn.kind == "executed" and turn.report.succeeded
    assert any("history" in w for w in turn.report.warnings)