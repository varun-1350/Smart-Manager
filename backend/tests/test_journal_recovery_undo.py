import hashlib
import os
from pathlib import Path

import pytest

from backend.execution.approval import grant
from backend.execution.engine import Tools, execute
from backend.execution.file_journal import (FileJournal, acknowledge, find_interrupted,
                                            list_runs, read_journal)
from backend.execution.prepare import Operation, prepare
from backend.execution.recovery import recovery_report
from backend.execution.undo import run_undo
from backend.planner.actions import APPROVAL_RISKS
from backend.planner.validator import BASE_RISK
from backend.schemas.plan import ExecutionPlan
from backend.schemas.task import Task
from backend.security.config import SecurityConfig
from backend.security.paths import PathPolicy
from backend.tools.filesystem import textedit


class Env:
    pass


@pytest.fixture
def env(tmp_path):
    base = tmp_path.resolve()
    e = Env()
    e.base = base
    e.dl, e.docs, e.work = base / "Downloads", base / "Documents", base / "Work"
    e.app, e.outside = e.work / "Projects" / "App", base / "Outside"
    for d in (e.dl / "sub", e.docs / "Archive", e.app, e.outside):
        d.mkdir(parents=True)
    (e.dl / "a.pdf").write_bytes(b"x" * 10)
    (e.dl / "notes.txt").write_bytes(b"xxxxx")
    (e.outside / "x.txt").write_bytes(b"1")
    e.policy = PathPolicy(SecurityConfig(allowed_roots=(e.dl, e.docs, e.work),
                                         protected_paths=(e.app,), default_scope=e.dl))
    return e


def T(tid, action, params, deps=()):
    risk = BASE_RISK[action]
    return Task(task_id=tid, action=action, parameters=params, dependencies=list(deps),
                risk_level=risk, approval_required=risk in APPROVAL_RISKS)


def plan(*tasks):
    return ExecutionPlan(plan_id="p", request_id="r", tasks=list(tasks))


def run_plan(env, pl, journal=None, **kw):
    return execute(pl, env.policy, grant(prepare(pl, env.policy)), tools=Tools(),
                   journal=journal, **kw)


def move_a(env):
    return plan(T("t1", "move_file", {"targets": [{"path": str(env.dl / "a.pdf")}],
                                      "destination": "Archive"}))


def op(action, source=None, destination=None, detail=None):
    return Operation("t1", action, source, destination, detail or {}, "high")


def crashed(env, operation):
    """A journal where the step started and the program died before it finished."""
    j = FileJournal(env.base / "journal")
    j.start("p", "d", [operation])
    j.before(0, operation)
    return j


# ------------------------------------------------------------------ journal
def test_a_full_run_is_recorded(env):
    j = FileJournal(env.base / "journal")
    rep = run_plan(env, move_a(env), journal=j)
    run = read_journal(j.path)
    assert rep.succeeded and run.finish_status == "completed" and not run.interrupted
    assert run.steps[0].op["action"] == "move_file" and run.steps[0].outcome["status"] == "done"
    assert run.operations[0]["action"] == "move_file" and not run.damaged


def test_edits_record_the_hash_from_before_the_change(env):
    j = FileJournal(env.base / "journal")
    pl = plan(T("t1", "edit_text_file", {"target": {"path": str(env.dl / "notes.txt")},
                                         "operation": "append", "text": "hi"}))
    run_plan(env, pl, journal=j, backup_dir=env.base / "bak")
    assert read_journal(j.path).steps[0].before_sha256 == hashlib.sha256(b"xxxxx").hexdigest()


def test_a_torn_last_line_is_a_normal_crash(env):
    j = crashed(env, op("move_file", str(env.dl / "a.pdf"), str(env.docs / "Archive" / "a.pdf")))
    with open(j.path, "a") as fh:
        fh.write('{"event":"after","ind')            # power cut mid-write, no newline
    run = read_journal(j.path)
    assert run.interrupted and not run.damaged and run.steps[0].outcome is None
    acknowledge(j.path, "seen")
    again = read_journal(j.path)
    assert not again.interrupted and again.finish_status == "interrupted_reviewed"


def test_damage_in_the_middle_is_flagged(env):
    j = FileJournal(env.base / "journal")
    j.start("p", "d", [])
    with open(j.path, "a") as fh:
        fh.write("garbage\n")
    j.finish("completed")
    run = read_journal(j.path)
    assert run.damaged and run.finish_status == "completed"


def test_finding_interrupted_runs_and_unreadable_files(env):
    done = FileJournal(env.base / "journal")
    done.start("p1", "d", [])
    done.finish("completed")
    crashed(env, op("open_file", str(env.dl / "a.pdf")))
    (env.base / "journal" / "broken.jsonl").write_text("not json\n")
    runs, errors = list_runs(env.base / "journal")
    assert len(runs) == 2 and len(errors) == 1 and "broken.jsonl" in errors[0]
    interrupted, _ = find_interrupted(env.base / "journal")
    assert len(interrupted) == 1


def test_a_hostile_plan_id_cannot_escape_the_journal_folder(env):
    j = FileJournal(env.base / "journal")
    j.start("../../evil", "d", [])
    assert j.path.parent == env.base / "journal"


# ----------------------------------------------------------------- recovery
def test_crash_after_a_move_is_detected_and_undoable(env):
    src, dst = env.dl / "a.pdf", env.docs / "Archive" / "a.pdf"
    j = crashed(env, op("move_file", str(src), str(dst)))
    os.rename(src, dst)                                    # the move happened, then the crash
    rep = recovery_report(read_journal(j.path))
    assert rep.unknown[0].state == "done"
    assert rep.undo_steps == [{"op": "move_back", "from": str(dst), "to": str(src)}]
    assert [o.status for o in run_undo(rep.undo_steps, env.policy)] == ["undone"]
    assert src.exists() and not dst.exists()


def test_crash_before_a_move_changes_nothing(env):
    j = crashed(env, op("move_file", str(env.dl / "a.pdf"), str(env.docs / "Archive" / "a.pdf")))
    s = recovery_report(read_journal(j.path)).unknown[0]
    assert s.state == "not_done" and s.undo is None


def test_file_in_both_places_is_unclear(env):
    src, dst = env.dl / "a.pdf", env.docs / "Archive" / "a.pdf"
    dst.write_bytes(b"copy")
    j = crashed(env, op("move_file", str(src), str(dst)))
    assert recovery_report(read_journal(j.path)).unknown[0].state == "unclear"


def test_crash_around_a_create(env):
    target = env.dl / "Fresh"
    j = crashed(env, op("create_folder", None, str(target)))
    assert recovery_report(read_journal(j.path)).unknown[0].state == "not_done"
    target.mkdir()
    rep = recovery_report(read_journal(j.path))
    assert rep.unknown[0].state == "done" and rep.undo_steps[0]["op"] == "remove_empty_folder"


def test_crash_around_a_delete(env):
    f = env.dl / "a.pdf"
    j = crashed(env, op("move_to_recycle_bin", str(f)))
    assert recovery_report(read_journal(j.path)).unknown[0].state == "not_done"
    f.unlink()
    rep = recovery_report(read_journal(j.path))
    assert rep.unknown[0].state == "done" and rep.undo_steps[0]["manual"] is True


def test_crash_around_an_edit_with_a_backup(env):
    f = env.dl / "notes.txt"
    j = crashed(env, op("edit_text_file", str(f), None, {"operation": "append", "text": "hi"}))
    assert recovery_report(read_journal(j.path)).unknown[0].state == "not_done"
    textedit.edit_text(f, "append", text="hi", backup_dir=env.base / "bak")   # edit, then crash
    rep = recovery_report(read_journal(j.path), env.base / "bak")
    state = rep.unknown[0]
    assert state.state == "unclear" and state.undo["op"] == "restore_backup"
    assert rep.undo_steps == []                          # uncertain, so never offered automatically
    assert [o.status for o in run_undo([state.undo], env.policy)] == ["undone"]
    assert f.read_bytes() == b"xxxxx"


def test_edit_crash_without_a_backup_has_no_undo(env):
    f = env.dl / "notes.txt"
    j = crashed(env, op("edit_text_file", str(f), None, {"operation": "append", "text": "hi"}))
    textedit.edit_text(f, "append", text="hi")
    state = recovery_report(read_journal(j.path), env.base / "bak").unknown[0]
    assert state.state == "unclear" and state.undo is None


def test_open_steps_are_harmless(env):
    j = crashed(env, op("open_file", str(env.dl / "a.pdf")))
    assert recovery_report(read_journal(j.path)).unknown[0].state == "harmless"


def test_a_finished_run_can_be_undone_later(env):
    j = FileJournal(env.base / "journal")
    run_plan(env, move_a(env), journal=j)
    rep = recovery_report(read_journal(j.path))
    assert rep.unknown == [] and rep.undo_steps[0]["op"] == "move_back"
    assert [o.status for o in run_undo(rep.undo_steps, env.policy)] == ["undone"]
    assert (env.dl / "a.pdf").exists()


# --------------------------------------------------------------------- undo
def test_undo_a_move_and_refuse_when_the_place_is_taken(env):
    src, dst = env.dl / "a.pdf", env.docs / "Archive" / "a.pdf"
    run_plan(env, move_a(env))
    step = {"op": "move_back", "from": str(dst), "to": str(src)}
    src.write_bytes(b"someone else's file")
    out = run_undo([step], env.policy)[0]
    assert out.status == "failed" and "exists" in out.message and dst.exists()
    src.unlink()
    assert run_undo([step], env.policy)[0].status == "undone" and src.exists()


def test_undo_will_not_touch_files_outside_the_allowed_folders(env):
    step = {"op": "move_back", "from": str(env.outside / "x.txt"), "to": str(env.dl / "x.txt")}
    assert run_undo([step], env.policy)[0].status == "failed"
    assert (env.outside / "x.txt").exists()


def test_remove_empty_folder_only_when_empty(env):
    folder = env.dl / "Fresh"
    folder.mkdir()
    step = {"op": "remove_empty_folder", "path": str(folder)}
    (folder / "keep.txt").write_bytes(b"1")
    assert run_undo([step], env.policy)[0].status == "failed" and folder.exists()
    (folder / "keep.txt").unlink()
    assert run_undo([step], env.policy)[0].status == "undone" and not folder.exists()


def test_remove_empty_file_only_when_empty(env):
    f = env.dl / "new.txt"
    f.write_bytes(b"")
    step = {"op": "remove_empty_file", "path": str(f)}
    f.write_bytes(b"user wrote this")
    assert run_undo([step], env.policy)[0].status == "failed" and f.exists()
    f.write_bytes(b"")
    assert run_undo([step], env.policy)[0].status == "undone" and not f.exists()


def test_undo_an_edit_end_to_end_and_refuse_after_later_changes(env):
    f = env.dl / "notes.txt"
    pl = plan(T("t1", "edit_text_file", {"target": {"path": str(f)},
                                         "operation": "append", "text": "hi"}))
    rep = run_plan(env, pl, backup_dir=env.base / "bak")
    assert f.read_bytes() == b"xxxxx\nhi\n"
    f.write_bytes(b"xxxxx\nhi\nsomeone typed more\n")
    out = run_undo(rep.undo_steps(), env.policy)[0]
    assert out.status == "failed" and "changed" in out.message
    f.write_bytes(b"xxxxx\nhi\n")
    assert run_undo(rep.undo_steps(), env.policy)[0].status == "undone"
    assert f.read_bytes() == b"xxxxx"


def test_undo_in_newest_first_order(env):
    pl = plan(T("t1", "create_folder", {"name": "Fresh"}),
              T("t2", "move_file", {"targets": [{"path": str(env.dl / "a.pdf")}],
                                    "destination": "Fresh"}, ["t1"]))
    rep = run_plan(env, pl)
    assert (env.dl / "Fresh" / "a.pdf").exists()
    steps = rep.undo_steps()
    assert [s["op"] for s in steps] == ["move_back", "remove_empty_folder"]
    assert [o.status for o in run_undo(steps, env.policy)] == ["undone", "undone"]
    assert (env.dl / "a.pdf").exists() and not (env.dl / "Fresh").exists()


def test_manual_unknown_and_malformed_steps(env):
    out = run_undo([{"op": "restore_from_recycle_bin", "path": str(env.dl / "a.pdf")},
                    {"op": "format_the_disk"},
                    {"op": "move_back"}], env.policy)
    assert [o.status for o in out] == ["manual", "failed", "failed"]