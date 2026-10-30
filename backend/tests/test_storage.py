import sqlite3
import threading

import pytest

from backend.storage.db import SCHEMA_VERSION, Database
from backend.storage.history import HistoryStore
from backend.storage.settings import SettingsStore


@pytest.fixture
def stores(tmp_path):
    db = Database(tmp_path / "data" / "app.db")
    settings = SettingsStore(db)
    return db, settings, HistoryStore(db, settings)


def rec(h, text="x", **kw):
    args = dict(request=text, kind="executed", status="completed", summary="s")
    args.update(kw)
    return h.record(**args)


# ------------------------------------------------------------------- database
def test_schema_is_created_and_reopening_is_harmless(tmp_path):
    path = tmp_path / "d" / "a.db"
    Database(path)
    db = Database(path)
    with db.connection() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"history", "settings"} <= tables


def test_a_damaged_file_is_set_aside_not_deleted(tmp_path):
    path = tmp_path / "a.db"
    path.write_bytes(b"this is not a database" * 50)
    db = Database(path)
    assert db.quarantined is not None
    assert db.quarantined.read_bytes().startswith(b"this is not a database")
    settings = SettingsStore(db)
    assert rec(HistoryStore(db, settings)) is None            # the fresh database works


def test_a_database_from_a_newer_version_is_refused_and_left_alone(tmp_path):
    path = tmp_path / "a.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t(x)")
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.DatabaseError, match="newer"):
        Database(path)
    assert path.exists() and not list(tmp_path.glob("*.corrupt-*"))


# ------------------------------------------------------------------- settings
def test_settings_defaults_and_changes(stores):
    _, settings, _ = stores
    assert settings.get("history_enabled") is True
    settings.set("history_enabled", False)
    assert settings.get("history_enabled") is False
    described = settings.describe()[0]
    assert described["key"] == "history_enabled" and described["type"] == "bool"
    assert described["value"] is False


def test_settings_reject_unknown_keys_and_non_booleans(stores):
    _, settings, _ = stores
    for call in (lambda: settings.get("nope"), lambda: settings.set("nope", True)):
        with pytest.raises(KeyError):
            call()
    for bad in ("yes", 1, None):
        with pytest.raises(TypeError):
            settings.set("history_enabled", bad)


def test_a_garbage_stored_value_falls_back_to_the_default(stores):
    db, settings, _ = stores
    with db.connection() as conn:
        conn.execute("INSERT INTO settings(key, value) VALUES ('history_enabled', 'maybe')")
    assert settings.get("history_enabled") is True


# -------------------------------------------------------------------- history
def test_newest_first_and_paging(stores):
    _, _, h = stores
    for i in range(7):
        assert rec(h, f"req {i}") is None
    page1, nxt = h.recent(3)
    assert [i["request"] for i in page1] == ["req 6", "req 5", "req 4"] and nxt == page1[-1]["id"]
    page2, nxt2 = h.recent(3, nxt)
    assert [i["request"] for i in page2] == ["req 3", "req 2", "req 1"]
    page3, nxt3 = h.recent(3, nxt2)
    assert [i["request"] for i in page3] == ["req 0"] and nxt3 is None


def test_text_is_stored_literally_and_capped(stores):
    _, _, h = stores
    evil = "x'); DROP TABLE history;--"
    rec(h, evil)
    assert h.recent(5)[0][0]["request"] == evil
    rec(h, "a\x00b", summary="s" * 50_000)
    assert h.get(2)["request"] == "ab" and len(h.get(2)["summary"]) == HistoryStore.MAX_SUMMARY
    rec(h, "r" * 5000)
    assert len(h.get(3)["request"]) == HistoryStore.MAX_REQUEST
    assert len(h.recent(5)[0][0]["preview"]) <= HistoryStore.PREVIEW


def test_changed_flag_and_detail_fields(stores):
    _, _, h = stores
    rec(h, "move it", changed=True, plan_id="p1", journal="j.jsonl")
    item = h.get(1)
    assert item["changed"] is True and item["plan_id"] == "p1" and item["journal"] == "j.jsonl"
    assert h.get(999) is None


def test_old_entries_are_dropped_beyond_the_limit(stores):
    db, settings, _ = stores
    h = HistoryStore(db, settings, max_rows=3)
    for i in range(6):
        rec(h, f"r{i}")
    assert [i["request"] for i in h.recent(10)[0]] == ["r5", "r4", "r3"]


def test_turning_history_off_stops_recording(stores):
    _, settings, h = stores
    settings.set("history_enabled", False)
    assert rec(h) is None and h.recent(5) == ([], None)


def test_clear(stores):
    _, _, h = stores
    for i in range(3):
        rec(h, f"r{i}")
    assert h.clear() == 3 and h.recent(5) == ([], None)


def test_a_database_failure_is_reported_not_raised(stores, monkeypatch):
    db, _, h = stores

    def boom():
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(db, "connection", boom)
    message = rec(h)
    assert message and "couldn't save" in message


def test_writes_from_several_threads_are_all_saved(stores):
    _, _, h = stores

    def work(n):
        for i in range(15):
            rec(h, f"t{n}-{i}")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(h.recent(200)[0]) == 60