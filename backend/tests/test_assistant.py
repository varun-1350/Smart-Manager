import shutil
from datetime import date
from pathlib import Path

import pytest

from backend.execution.file_journal import FileJournal
from backend.execution.engine import Tools
from backend.execution.prepare import Operation
from backend.nlp.confidence import Confidence
from backend.security.config import SecurityConfig
from backend.security.paths import PathPolicy
from backend.services.assistant import Assistant
from backend.tools.filesystem import files, system

TEXT = "Find PDFs in Downloads, open the largest, and move the rest to Archive"


class FakeClassifier:
    """Maps the first word to an intent, so these tests exercise the wiring, not the ML."""
    MAP = {"find": "SEARCH", "open": "OPEN", "move": "MOVE", "delete": "DELETE",
           "list": "LIST", "create": "CREATE_FOLDER", "rename": "RENAME"}

    def predict(self, text):
        intent = self.MAP.get(text.split()[0].lower(), "UNSUPPORTED")
        return Confidence(intent, 0.95, "UNSUPPORTED", 0.9)


class Env:
    pass


@pytest.fixture
def env(tmp_path):
    base = tmp_path.resolve()
    e = Env()
    e.base = base
    e.dl, e.docs, e.work = base / "Downloads", base / "Documents", base / "Work"
    e.app, e.outside = e.work / "Projects" / "App", base / "Outside"
    for d in (e.dl / "sub", e.docs / "Archive", e.app, e.outside, base / "bin"):
        d.mkdir(parents=True)
    for path, size in ((e.dl / "a.pdf", 10), (e.dl / "b.pdf", 100), (e.dl / "sub" / "c.pdf", 50),
                       (e.dl / "notes.txt", 5), (e.dl / "setup.exe", 1)):
        path.write_bytes(b"x" * size)
    e.policy = PathPolicy(SecurityConfig(allowed_roots=(e.dl, e.docs, e.work),
                                         protected_paths=(e.app,), default_scope=e.dl))
    e.opened = []
    return e


def make_assistant(env, **kw):
    bin_dir = env.base / "bin"
    tools = Tools(
        open_path=lambda p: system.open_path(p, opener=env.opened.append),
        move_to_recycle_bin=lambda p: files.move_to_recycle_bin(
            p, trash=lambda x: shutil.move(x, str(bin_dir / Path(x).name))))
    return Assistant(FakeClassifier(), env.policy, journal_dir=env.base / "journal",
                     backup_dir=env.base / "bak", tools=tools,
                     today=lambda: date(2026, 10, 28), **kw)


def test_full_conversation_from_sentence_to_moved_files(env):
    a = make_assistant(env)
    turn = a.handle(TEXT)
    assert turn.kind == "needs_approval" and turn.digest
    assert "Planned changes" in turn.message
    assert (env.dl / "a.pdf").exists() and env.opened == []          # nothing happened yet
    done = a.approve(turn.turn_id, turn.digest)
    assert done.kind == "executed" and done.report.succeeded
    assert (env.docs / "Archive" / "a.pdf").exists() and (env.docs / "Archive" / "c.pdf").exists()
    assert (env.dl / "b.pdf").exists() and env.opened == [str(env.dl / "b.pdf")]
    assert len(list((env.base / "journal").glob("*.jsonl"))) == 1


def test_wrong_digest_does_nothing_and_the_real_one_still_works(env):
    a = make_assistant(env)
    turn = a.handle(TEXT)
    assert a.approve(turn.turn_id, "0" * 64).kind == "error"
    assert a.approve(turn.turn_id, "").kind == "error"
    assert (env.dl / "a.pdf").exists()
    assert a.approve(turn.turn_id, turn.digest).kind == "executed"


def test_unknown_turn_and_double_approval(env):
    a = make_assistant(env)
    assert a.approve("nope", "x").kind == "error"
    turn = a.handle(TEXT)
    assert a.approve(turn.turn_id, turn.digest).kind == "executed"
    assert a.approve(turn.turn_id, turn.digest).kind == "error"       # one approval, one run


def test_pending_requests_expire(env):
    now = [1000.0]
    a = make_assistant(env, clock=lambda: now[0])
    turn = a.handle(TEXT)
    now[0] += 301
    assert "no longer waiting" in a.approve(turn.turn_id, turn.digest).message
    assert (env.dl / "a.pdf").exists()


def test_files_changing_between_preview_and_approval_blocks_the_run(env):
    a = make_assistant(env)
    turn = a.handle(TEXT)
    (env.dl / "z.pdf").write_bytes(b"x" * 500)                         # a new largest file
    result = a.approve(turn.turn_id, turn.digest)
    assert result.kind == "error" and "changed" in result.message
    assert (env.dl / "a.pdf").exists() and env.opened == []


def test_reading_and_opening_need_no_approval(env):
    a = make_assistant(env)
    turn = a.handle("Find PDFs in Downloads")
    assert turn.kind == "executed" and turn.report.results[0].output["count"] == 3
    assert a.handle("Open b.pdf").kind == "executed" and env.opened == [str(env.dl / "b.pdf")]


def test_each_failure_kind_is_reported(env):
    a = make_assistant(env)
    assert a.handle("").kind == "clarify"
    assert a.handle("Delete").kind == "clarify"
    assert a.handle("What is the weather").kind == "unsupported"
    assert a.handle("Open setup.exe").kind == "blocked"                 # programs are never opened
    assert a.handle("Delete a.pdf in Downloads").kind == "error"        # folder not honoured yet
    assert a.handle("x" * 5000).kind == "error" and a.handle("a\x00b").kind == "error"
    assert (env.dl / "a.pdf").exists()


def test_a_busy_assistant_refuses_instead_of_overlapping(env):
    a = make_assistant(env)
    a._lock.acquire()
    try:
        turn = a.handle("Find PDFs in Downloads")
    finally:
        a._lock.release()
    assert turn.kind == "error" and "still running" in turn.message


def test_undo_needs_confirmation_and_restores_everything(env):
    a = make_assistant(env)
    assert a.undo_preview() == [] and a.undo_last(confirmed=True) == []
    turn = a.handle(TEXT)
    a.approve(turn.turn_id, turn.digest)
    assert len(a.undo_preview()) == 2
    with pytest.raises(PermissionError):
        a.undo_last()
    outcomes = a.undo_last(confirmed=True)
    assert [o.status for o in outcomes] == ["undone", "undone"]
    assert (env.dl / "a.pdf").exists() and (env.dl / "sub" / "c.pdf").exists()
    assert not (env.docs / "Archive" / "a.pdf").exists()
    assert a.undo_last(confirmed=True) == []                            # nothing left to undo
    assert '"event":"undo"' in next((env.base / "journal").glob("*.jsonl")).read_text()


def test_interrupted_runs_are_reported_once(env):
    src, dst = env.dl / "a.pdf", env.docs / "Archive" / "a.pdf"
    j = FileJournal(env.base / "journal")
    operation = Operation("t1", "move_file", str(src), str(dst), {}, "high")
    j.start("p", "d", [operation])
    j.before(0, operation)
    src.rename(dst)                                                     # crash right after
    a = make_assistant(env)
    reports, errors = a.interrupted()
    assert errors == [] and len(reports) == 1
    assert reports[0].unknown[0].state == "done" and len(reports[0].undo_steps) == 1
    a.dismiss_interrupted(reports[0].run_path)
    assert a.interrupted() == ([], [])