import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from backend.execution.approval import ApprovalError, grant
from backend.execution.engine import Tools, execute, guard
from backend.execution.journal import MemoryJournal, NullJournal
from backend.execution.prepare import Operation, prepare
from backend.planner.actions import APPROVAL_RISKS
from backend.planner.validator import BASE_RISK
from backend.schemas.plan import ExecutionPlan, PlanStatus
from backend.schemas.result import VerificationStatus
from backend.schemas.task import Task
from backend.security.config import SecurityConfig
from backend.security.paths import PathPolicy
from backend.tools.filesystem import files, system
from backend.tools.filesystem.common import ToolError


class Env:
    pass


class FakeClipboard:
    def __init__(self):
        self.text = None

    def set(self, text):
        self.text = text

    def get(self):
        return self.text


@pytest.fixture
def env(tmp_path):
    base = tmp_path.resolve()
    e = Env()
    e.base = base
    e.dl, e.docs, e.work = base / "Downloads", base / "Documents", base / "Work"
    e.app = e.work / "Projects" / "App"
    e.outside = base / "Outside"
    for d in (e.dl / "sub", e.docs / "Archive", e.app, e.outside, base / "bin"):
        d.mkdir(parents=True)

    def put(path, size):
        path.write_bytes(b"x" * size)

    put(e.dl / "a.pdf", 10)
    put(e.dl / "b.pdf", 100)
    put(e.dl / "sub" / "c.pdf", 50)
    put(e.dl / "notes.txt", 5)
    put(e.dl / "photo.jpg", 7)
    put(e.dl / "setup.exe", 1)
    put(e.app / "key.pdf", 9)
    put(e.outside / "x.pdf", 1)
    e.put = put
    e.policy = PathPolicy(SecurityConfig(allowed_roots=(e.dl, e.docs, e.work),
                                         protected_paths=(e.app,), default_scope=e.dl))
    e.opened, e.clip = [], FakeClipboard()
    return e


def make_tools(env, **over):
    bin_dir = env.base / "bin"
    params = dict(
        open_path=lambda p: system.open_path(p, opener=env.opened.append),
        copy_path_to_clipboard=lambda p: system.copy_path_to_clipboard(p, clipboard=env.clip),
        move_to_recycle_bin=lambda p: files.move_to_recycle_bin(
            p, trash=lambda x: shutil.move(x, str(bin_dir / Path(x).name))),
    )
    params.update(over)
    return Tools(**params)


def T(tid, action, params, deps=(), approval=None):
    risk = BASE_RISK[action]
    needs = risk in APPROVAL_RISKS if approval is None else approval
    return Task(task_id=tid, action=action, parameters=params, dependencies=list(deps),
                risk_level=risk, approval_required=needs)


def plan(*tasks):
    return ExecutionPlan(plan_id="p", request_id="r", tasks=list(tasks))


def search(env):
    return T("t1", "search_files", {"filenames": [], "names": [], "file_types": ["pdf"],
                                    "date_filter": None, "scope": {"path": str(env.dl)}})


def flow(env):
    return plan(
        search(env),
        T("t2", "open_file", {"target": {"from_task": "t1", "select": "largest"}},
          ["t1"], approval=True),
        T("t3", "move_file",
          {"targets": [{"from_task": "t1", "select": "remaining", "except_tasks": ["t2"]}],
           "destination": "Archive"}, ["t1", "t2"]))


def move3(env, *extra):
    targets = [{"path": str(env.dl / n)} for n in ("a.pdf", "notes.txt", "photo.jpg")]
    return plan(T("t1", "move_file", {"targets": targets, "destination": "Archive"}), *extra)


def move_a(env):
    return plan(T("t1", "move_file",
                  {"targets": [{"path": str(env.dl / "a.pdf")}], "destination": "Archive"}))


def run(env, pl, tools=None, approve=True, **kw):
    ap = grant(prepare(pl, env.policy)) if approve else None
    return execute(pl, env.policy, ap, tools=tools or make_tools(env), **kw)


def flaky_move(fail_on=2):
    calls = []

    def move(src, dst, **kw):
        calls.append(src)
        if len(calls) == fail_on:
            raise ToolError("disk exploded")
        return files.move_path(src, dst, **kw)
    return move


# ----------------------------------------------------------------- happy paths
def test_full_flow_find_open_largest_move_rest(env):
    rep = run(env, flow(env))
    assert rep.succeeded and rep.status == PlanStatus.COMPLETED
    assert env.opened == [str(env.dl / "b.pdf")]
    assert (env.docs / "Archive" / "a.pdf").exists() and (env.docs / "Archive" / "c.pdf").exists()
    assert not (env.dl / "a.pdf").exists() and not (env.dl / "sub" / "c.pdf").exists()
    assert (env.dl / "b.pdf").exists()
    assert [r.status for r in rep.results] == ["success"] * 3
    assert {r.task_id: r.verification_status for r in rep.results} == {
        "t1": VerificationStatus.VERIFIED,
        "t2": VerificationStatus.NOT_CHECKED,       # opening can't be verified
        "t3": VerificationStatus.VERIFIED}
    assert len(rep.undo_steps()) == 2 and not rep.partial
    assert "Move" in rep.summary()


def test_read_only_plan_needs_no_approval(env):
    rep = execute(plan(search(env)), env.policy, None, tools=make_tools(env))
    assert rep.succeeded and rep.results[0].output["count"] == 3 and rep.outcomes == []


def test_open_and_clipboard_need_no_approval(env):
    f = env.dl / "a.pdf"
    rep = execute(plan(T("t1", "open_file", {"target": {"path": str(f)}})),
                  env.policy, None, tools=make_tools(env))
    assert rep.succeeded and env.opened == [str(f)]
    execute(plan(T("t1", "copy_path_to_clipboard", {"target": {"path": str(f)}})),
            env.policy, None, tools=make_tools(env))
    assert env.clip.text == str(f)


def test_delete_goes_to_the_recycle_bin(env):
    rep = run(env, plan(T("t1", "move_to_recycle_bin",
                          {"targets": [{"path": str(env.dl / "photo.jpg")}]})))
    assert rep.succeeded and not (env.dl / "photo.jpg").exists()
    assert (env.base / "bin" / "photo.jpg").exists()
    assert rep.outcomes[0].undo["op"] == "restore_from_recycle_bin"


def test_move_into_the_same_folder_is_a_noop(env):
    rep = run(env, plan(T("t1", "move_file", {"targets": [{"path": str(env.dl / "a.pdf")}],
                                              "destination": "Downloads"})))
    assert rep.succeeded and rep.outcomes[0].status == "unchanged"
    assert (env.dl / "a.pdf").exists() and not rep.changed_something


def test_create_then_edit_the_new_file(env):
    pl = plan(T("t1", "create_text_file", {"name": "todo.txt"}),
              T("t2", "edit_text_file",
                {"target": {"from_task": "t1", "select": "created"},
                 "operation": "append", "text": "buy milk"}, ["t1"], approval=True))
    rep = run(env, pl, backup_dir=env.base / "bak")
    assert rep.succeeded and (env.dl / "todo.txt").read_bytes() == b"buy milk\n"


# ------------------------------------------------------------------- edits
def edit_plan(env):
    return plan(T("t1", "edit_text_file", {"target": {"path": str(env.dl / "notes.txt")},
                                           "operation": "append", "text": "hi"}))


def test_edit_with_backup(env):
    rep = run(env, edit_plan(env), backup_dir=env.base / "bak")
    assert rep.succeeded and (env.dl / "notes.txt").read_bytes() == b"xxxxx\nhi\n"
    assert rep.outcomes[0].undo["op"] == "restore_backup"
    assert Path(rep.outcomes[0].undo["backup"]).read_bytes() == b"xxxxx"


def test_edit_without_a_backup_folder_is_refused(env):
    rep = run(env, edit_plan(env))
    assert rep.status == PlanStatus.FAILED and "backup" in rep.outcomes[0].message
    assert (env.dl / "notes.txt").read_bytes() == b"xxxxx"


# --------------------------------------------------------------- approval gate
def test_no_approval_means_nothing_runs(env):
    with pytest.raises(ApprovalError):
        execute(flow(env), env.policy, None, tools=make_tools(env))
    assert (env.dl / "a.pdf").exists() and env.opened == []


def test_files_changed_since_approval_means_nothing_runs(env):
    pl = flow(env)
    ap = grant(prepare(pl, env.policy))
    env.put(env.dl / "z.pdf", 500)                        # a new largest file
    with pytest.raises(ApprovalError, match="changed"):
        execute(pl, env.policy, ap, tools=make_tools(env))
    assert (env.dl / "a.pdf").exists() and env.opened == []


def test_plan_with_problems_never_runs(env):
    pl = plan(T("t1", "move_to_recycle_bin", {"targets": [{"path": str(env.outside / "x.pdf")}]}))
    with pytest.raises(ApprovalError):
        execute(pl, env.policy, None, tools=make_tools(env))
    assert (env.outside / "x.pdf").exists()


# ----------------------------------------------------- failure and cancellation
def test_failure_stops_the_task_and_skips_dependents(env):
    pl = move3(env, T("t2", "create_folder", {"name": "After"}, ["t1"]))
    rep = run(env, pl, make_tools(env, move_path=flaky_move()))
    assert rep.status == PlanStatus.FAILED and rep.partial
    assert [o.status for o in rep.outcomes] == ["done", "failed", "skipped"]
    assert [r.status for r in rep.results] == ["failed", "cancelled"]
    assert rep.results[0].verification_status == VerificationStatus.FAILED
    assert (env.docs / "Archive" / "a.pdf").exists()        # the first move really happened
    assert (env.dl / "notes.txt").exists() and (env.dl / "photo.jpg").exists()
    assert not (env.dl / "After").exists()                  # the dependent never ran
    assert "disk exploded" in rep.summary()


def test_unexpected_exceptions_are_reported_not_raised(env):
    def explode(src, dst, **kw):
        raise RuntimeError("boom")
    rep = run(env, move_a(env), make_tools(env, move_path=explode))
    assert rep.status == PlanStatus.FAILED
    assert "Unexpected error (RuntimeError)" in rep.outcomes[0].message
    assert rep.outcomes[0].partial is not None


def test_cancellation_stops_between_operations(env):
    n = {"calls": 0}

    def cancel():
        n["calls"] += 1
        return n["calls"] > 2           # before the task, before op 0, then cancelled before op 1

    rep = run(env, move3(env), cancel=cancel)
    assert rep.status == PlanStatus.CANCELLED and rep.partial
    assert [o.status for o in rep.outcomes] == ["done", "skipped", "skipped"]
    assert rep.results[0].status == "cancelled"
    assert (env.docs / "Archive" / "a.pdf").exists() and (env.dl / "notes.txt").exists()


def test_progress_callback_and_a_broken_callback(env):
    seen = []
    run(env, move_a(env), on_progress=lambda tid, st: seen.append((tid, st)))
    assert seen == [("t1", "running"), ("t1", "success")]

    def broken(tid, st):
        raise RuntimeError("ui crashed")
    env.put(env.dl / "a.pdf", 10)
    # the first run moved a.pdf, so recreate the situation with another plan
    rep = run(env, plan(T("t1", "create_folder", {"name": "Fresh"})), on_progress=broken)
    assert rep.succeeded and (env.dl / "Fresh").is_dir()


# ------------------------------------------------------------------- journal
def test_journal_records_intent_before_the_change(env):
    journal, spied = MemoryJournal(), []

    def spying_move(src, dst, **kw):
        spied.append(journal.events[-1])            # the last event when the tool is called
        return files.move_path(src, dst, **kw)

    rep = run(env, move_a(env), make_tools(env, move_path=spying_move), journal=journal)
    assert rep.succeeded and spied == [("before", 0)]
    assert [e[0] for e in journal.events] == ["start", "before", "after", "finish"]
    assert journal.events[-1] == ("finish", "completed")


class BrokenBefore(NullJournal):
    def before(self, index, op):
        raise OSError("disk full")


class BrokenAfter(NullJournal):
    def after(self, index, op, outcome):
        raise OSError("disk full")


def test_if_the_journal_cannot_record_intent_nothing_is_changed(env):
    rep = run(env, move_a(env), journal=BrokenBefore())
    assert rep.status == PlanStatus.FAILED and "journal" in rep.outcomes[0].message
    assert (env.dl / "a.pdf").exists() and not (env.docs / "Archive" / "a.pdf").exists()


def test_journal_failure_after_a_change_is_reported_as_a_warning(env):
    rep = run(env, move_a(env), journal=BrokenAfter())
    assert rep.succeeded and (env.docs / "Archive" / "a.pdf").exists()
    assert rep.warnings and "journal" in rep.warnings[0]


# --------------------------------------------------- the last-moment re-check
def op(action, source=None, destination=None):
    return Operation("t1", action, source, destination, {}, "high")


def test_guard_blocks_unsafe_operations(env):
    D = env.dl
    assert guard(env.policy, op("move_to_recycle_bin", str(D / "a.pdf"))) == []
    assert guard(env.policy, op("move_file", str(D / "a.pdf"), str(env.docs / "Archive" / "a.pdf"))) == []
    assert guard(env.policy, op("move_to_recycle_bin", str(env.outside / "x.pdf")))
    assert guard(env.policy, op("move_to_recycle_bin", str(env.app / "key.pdf")))
    assert guard(env.policy, op("move_to_recycle_bin", str(D / "gone.pdf")))               # missing
    assert guard(env.policy, op("move_file", str(D / "a.pdf"), str(env.outside / "a.pdf")))
    assert guard(env.policy, op("move_file", str(D / "a.pdf"), str(D / "b.pdf")))          # exists
    assert guard(env.policy, op("move_file", str(D / "a.pdf"), str(env.docs / "nope" / "a.pdf")))
    assert guard(env.policy, op("rename_file", str(D / "a.pdf"), str(D / "a.exe")))
    assert guard(env.policy, op("create_text_file", None, str(D / "t.exe")))
    assert guard(env.policy, op("create_folder", None, str(env.outside / "New")))
    assert guard(env.policy, op("open_file", str(D / "setup.exe")))                         # program
    assert guard(env.policy, op("edit_text_file", str(D / "a.pdf")))                        # not text
    assert guard(env.policy, op("create_folder", None, str(D / "New"))) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows file names are case-insensitive")
def test_guard_allows_a_case_only_rename(env):
    assert guard(env.policy, op("rename_file", str(env.dl / "a.pdf"), str(env.dl / "A.pdf"))) == []