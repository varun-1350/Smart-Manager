import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.execution.engine import Tools
from backend.execution.file_journal import FileJournal
from backend.execution.prepare import Operation
from backend.nlp.confidence import Confidence
from backend.security.config import SecurityConfig
from backend.security.paths import PathPolicy
from backend.services.assistant import Assistant
from backend.tools.filesystem import files, system
from backend.storage.db import Database
from backend.storage.history import HistoryStore
from backend.storage.settings import SettingsStore

TOKEN = "t" * 32
H = {"X-Session-Token": TOKEN}
TEXT = "Find PDFs in Downloads, open the largest, and move the rest to Archive"


class FakeClassifier:
    MAP = {"find": "SEARCH", "open": "OPEN", "move": "MOVE", "delete": "DELETE",
           "list": "LIST", "create": "CREATE_FOLDER"}

    def predict(self, text):
        return Confidence(self.MAP.get(text.split()[0].lower(), "UNSUPPORTED"), 0.95,
                          "UNSUPPORTED", 0.9)


class Env:
    pass


@pytest.fixture
def env(tmp_path):
    base = tmp_path.resolve()
    e = Env()
    e.base = base
    e.dl, e.docs, e.work = base / "Downloads", base / "Documents", base / "Work"
    e.app_dir, e.outside = e.work / "Projects" / "App", base / "Outside"
    for d in (e.dl / "sub", e.docs / "Archive", e.app_dir, e.outside, base / "bin"):
        d.mkdir(parents=True)
    for path, size in ((e.dl / "a.pdf", 10), (e.dl / "b.pdf", 100), (e.dl / "sub" / "c.pdf", 50),
                       (e.dl / "notes.txt", 5)):
        path.write_bytes(b"x" * size)
    e.policy = PathPolicy(SecurityConfig(allowed_roots=(e.dl, e.docs, e.work),
                                         protected_paths=(e.app_dir,), default_scope=e.dl))
    e.opened = []
    bin_dir = base / "bin"
    tools = Tools(
        open_path=lambda p: system.open_path(p, opener=e.opened.append),
        move_to_recycle_bin=lambda p: files.move_to_recycle_bin(
            p, trash=lambda x: shutil.move(x, str(bin_dir / Path(x).name))))
    e.assistant = Assistant(FakeClassifier(), e.policy, journal_dir=base / "journal",
                            backup_dir=base / "bak", tools=tools,
                            today=lambda: date(2026, 10, 28))
    e.app = create_app(e.assistant, TOKEN)
    e.client = TestClient(e.app, base_url="http://127.0.0.1")
    return e


def post(env, path, body):
    return env.client.post(f"/api/{path}", json=body, headers=H)


# ------------------------------------------------------------------ security
def test_requests_without_the_right_token_are_refused(env):
    assert env.client.get("/api/undo").status_code == 401
    assert env.client.get("/api/undo", headers={"X-Session-Token": "wrong"}).status_code == 401
    assert env.client.post("/api/message", json={"text": "list files"}).status_code == 401
    assert env.client.get("/api/undo", headers=H).status_code == 200
    assert env.opened == [] and (env.dl / "a.pdf").exists()


def test_unexpected_host_names_are_refused(env):
    evil = TestClient(env.app, base_url="http://evil.example")
    assert evil.get("/api/undo", headers=H).status_code == 400


def test_docs_are_not_exposed(env):
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert env.client.get(p, headers=H).status_code == 404


def test_a_weak_token_is_rejected_at_startup(env):
    with pytest.raises(ValueError):
        create_app(env.assistant, "short")


def test_bad_bodies_are_rejected(env):
    assert post(env, "message", {"text": "hi", "extra": 1}).status_code == 422
    assert post(env, "message", {"text": "x" * 2500}).status_code == 422
    assert post(env, "approve", {"turn_id": "t", "digest": "short"}).status_code == 422
    assert post(env, "undo", {}).status_code == 422
    assert post(env, "message", {"text": "x" * 1500}).json()["kind"] == "error"   # the app's own limit


# ----------------------------------------------------------------------- flow
def test_listing_shows_file_names_not_just_a_count(env):
    turn = post(env, "message", {"text": "Find PDFs in Downloads"}).json()
    assert turn["kind"] == "executed" and turn["report"]["succeeded"]
    assert "a.pdf" in turn["message"] and "c.pdf" in turn["message"]


def test_message_approve_and_undo_over_http(env):
    turn = post(env, "message", {"text": TEXT}).json()
    assert turn["kind"] == "needs_approval" and len(turn["digest"]) == 64
    assert (env.dl / "a.pdf").exists() and env.opened == []

    bad = post(env, "approve", {"turn_id": turn["turn_id"], "digest": "0" * 64}).json()
    assert bad["kind"] == "error" and (env.dl / "a.pdf").exists()

    done = post(env, "approve", {"turn_id": turn["turn_id"], "digest": turn["digest"]}).json()
    assert done["kind"] == "executed" and done["report"]["succeeded"]
    assert (env.docs / "Archive" / "a.pdf").exists() and env.opened == [str(env.dl / "b.pdf")]
    assert done["report"]["undo_available"] is True

    assert len(env.client.get("/api/undo", headers=H).json()["steps"]) == 2
    assert post(env, "undo", {"confirm": False}).status_code == 400
    out = post(env, "undo", {"confirm": True}).json()["outcomes"]
    assert [o["status"] for o in out] == ["undone", "undone"]
    assert (env.dl / "a.pdf").exists() and (env.dl / "sub" / "c.pdf").exists()


def test_reject_discards_the_pending_request(env):
    turn = post(env, "message", {"text": TEXT}).json()
    assert post(env, "reject", {"turn_id": turn["turn_id"]}).json() == {"ok": True}
    again = post(env, "approve", {"turn_id": turn["turn_id"], "digest": turn["digest"]}).json()
    assert again["kind"] == "error" and (env.dl / "a.pdf").exists()


def test_a_busy_server_answers_409_but_cancel_still_works(env):
    env.app.state.gate.acquire()
    try:
        assert post(env, "message", {"text": "list files"}).status_code == 409
        assert post(env, "cancel", {}).status_code == 200
    finally:
        env.app.state.gate.release()
    assert post(env, "message", {"text": "list files"}).status_code == 200


# --------------------------------------------------------------- interrupted
def crash_a_move(env):
    src, dst = env.dl / "a.pdf", env.docs / "Archive" / "a.pdf"
    j = FileJournal(env.base / "journal")
    operation = Operation("t1", "move_file", str(src), str(dst), {}, "high")
    j.start("p", "d", [operation])
    j.before(0, operation)
    src.rename(dst)
    return src, dst


def test_interrupted_runs_over_http(env):
    src, dst = crash_a_move(env)
    data = env.client.get("/api/interrupted", headers=H).json()
    run = data["reports"][0]
    assert run["run_id"].endswith(".jsonl") and "\\" not in run["run_id"]
    assert str(env.base) not in str(run["run_id"])
    assert run["unknown"][0]["state"] == "done" and len(run["undo_preview"]) == 1

    assert post(env, "interrupted/undo", {"run_id": run["run_id"], "confirm": False}).status_code == 400
    out = post(env, "interrupted/undo", {"run_id": run["run_id"], "confirm": True}).json()["outcomes"]
    assert out[0]["status"] == "undone" and src.exists() and not dst.exists()

    assert post(env, "interrupted/dismiss", {"run_id": run["run_id"]}).status_code == 200
    assert env.client.get("/api/interrupted", headers=H).json()["reports"] == []


def test_unknown_or_hostile_run_ids_are_404(env):
    crash_a_move(env)
    for bad in ("nope.jsonl", r"..\..\secret.jsonl", str(env.base / "x.jsonl")):
        assert post(env, "interrupted/dismiss", {"run_id": bad}).status_code == 404
        assert post(env, "interrupted/undo", {"run_id": bad, "confirm": True}).status_code == 404


from backend.security.errors import SecurityError
from backend.serve import build_assistant


def test_security_headers_are_set(env):
    r = env.client.get("/api/undo", headers=H)
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"


def test_the_built_interface_is_served_but_the_api_stays_protected(env, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<h1>hello ui</h1>")
    client = TestClient(create_app(env.assistant, TOKEN, ui_dir=ui), base_url="http://127.0.0.1")
    assert "hello ui" in client.get("/").text
    assert client.get("/api/undo").status_code == 401
    assert client.get("/api/undo", headers=H).status_code == 200


def test_starting_on_real_folders_needs_an_explicit_flag():
    with pytest.raises(SecurityError):
        build_assistant(None, False)

@pytest.fixture
def hist(env):
    db = Database(env.base / "app.db")
    settings = SettingsStore(db)
    env.history = HistoryStore(db, settings)
    env.assistant.history = env.history          # create_app picks up history + settings from here
    env.client2 = TestClient(create_app(env.assistant, TOKEN), base_url="http://127.0.0.1")
    return env


def test_storage_endpoints_need_the_token(hist):
    for path in ("/api/history", "/api/history/1", "/api/settings"):
        assert hist.client2.get(path).status_code == 401
    assert hist.client2.post("/api/history/clear", json={"confirm": True}).status_code == 401


def test_history_over_http(hist):
    r = hist.client2.post("/api/message", json={"text": "Find PDFs in Downloads"}, headers=H)
    assert r.json()["kind"] == "executed"
    listing = hist.client2.get("/api/history", headers=H).json()
    item = listing["items"][0]
    assert item["request"] == "Find PDFs in Downloads" and item["status"] == "completed"
    assert item["changed"] is False and listing["next_before"] is None
    full = hist.client2.get(f"/api/history/{item['id']}", headers=H).json()
    assert "a.pdf" in full["summary"]
    assert hist.client2.get("/api/history/999", headers=H).status_code == 404


@pytest.mark.parametrize("path", ["/api/history/abc", "/api/history/0", "/api/history?limit=0",
                                  "/api/history?limit=500", "/api/history?before_id=-1",
                                  "/api/history?before_id=99999999999999999999"])
def test_bad_history_parameters_are_rejected(hist, path):
    assert hist.client2.get(path, headers=H).status_code == 422


def test_clearing_history_needs_confirmation(hist):
    hist.client2.post("/api/message", json={"text": "Find PDFs in Downloads"}, headers=H)
    bad = hist.client2.post("/api/history/clear", json={"confirm": False}, headers=H)
    assert bad.status_code == 400 and len(hist.client2.get("/api/history", headers=H).json()["items"]) == 1
    ok = hist.client2.post("/api/history/clear", json={"confirm": True}, headers=H)
    assert ok.json() == {"deleted": 1}
    assert hist.client2.get("/api/history", headers=H).json()["items"] == []


def test_settings_over_http(hist):
    rows = hist.client2.get("/api/settings", headers=H).json()["settings"]
    assert rows[0]["key"] == "history_enabled" and rows[0]["value"] is True
    out = hist.client2.post("/api/settings", json={"key": "history_enabled", "value": False}, headers=H)
    assert out.json()["settings"][0]["value"] is False
    hist.client2.post("/api/message", json={"text": "Find PDFs in Downloads"}, headers=H)
    assert hist.client2.get("/api/history", headers=H).json()["items"] == []
    assert hist.client2.post("/api/settings", json={"key": "nope", "value": True}, headers=H).status_code == 404
    for bad in ("yes", 1):
        assert hist.client2.post("/api/settings", json={"key": "history_enabled", "value": bad},
                                 headers=H).status_code == 422


def test_storage_endpoints_report_unavailable_when_not_configured(env):
    assert env.client.get("/api/history", headers=H).status_code == 503
    assert env.client.get("/api/settings", headers=H).status_code == 503

def test_the_approval_preview_is_structured(env):
    turn = post(env, "message", {"text": TEXT}).json()
    preview = turn["preview"]
    assert preview["reads"][0]["count"] == 3 and preview["needs_approval"] is True
    ops = preview["operations"]
    assert [o["action"] for o in ops] == ["open_file", "move_file", "move_file"]
    assert [o["risk"] for o in ops] == ["medium", "high", "high"]
    assert ops[1]["source"].endswith("a.pdf") and ops[1]["destination"].endswith("a.pdf")
    done = post(env, "approve", {"turn_id": turn["turn_id"], "digest": turn["digest"]}).json()
    assert done["preview"] is None


def test_progress_endpoint(env):
    assert env.client.get("/api/progress").status_code == 401
    assert env.client.get("/api/progress", headers=H).json() == {"running": False, "tasks": []}
    env.app.state.gate.acquire()
    try:                                        # stays reachable while a request is running
        assert env.client.get("/api/progress", headers=H).status_code == 200
    finally:
        env.app.state.gate.release()