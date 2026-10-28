import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from backend.execution.approval import Approval, ApprovalError, check, grant
from backend.execution.prepare import prepare
from backend.execution.selection import SelectionError, select
from backend.planner.actions import APPROVAL_RISKS
from backend.planner.validator import BASE_RISK
from backend.schemas.plan import ExecutionPlan
from backend.schemas.task import Task
from backend.security.config import SecurityConfig
from backend.security.pathutil import norm
from backend.security.paths import PathPolicy
from backend.tools.filesystem.scan import scan


def ts(y, m, d):
    return datetime(y, m, d, 12).timestamp()


class Env:
    pass


@pytest.fixture
def env(tmp_path):
    base = tmp_path.resolve()
    e = Env()
    e.dl, e.docs, e.work = base / "Downloads", base / "Documents", base / "Work"
    e.app = e.work / "Projects" / "App"          # protected
    e.outside = base / "Outside"
    for d in (e.dl / "sub", e.docs / "Archive", e.app, e.outside):
        d.mkdir(parents=True)

    def put(path, size, when=None):
        path.write_bytes(b"x" * size)
        if when:
            os.utime(path, (when, when))

    put(e.dl / "a.pdf", 10, ts(2026, 9, 1))
    put(e.dl / "b.pdf", 100, ts(2026, 10, 10))
    put(e.dl / "sub" / "c.pdf", 50, ts(2026, 10, 20))
    put(e.dl / "notes.txt", 5, ts(2026, 10, 5))
    put(e.dl / "photo.jpg", 7)
    put(e.work / "w.pdf", 3)
    put(e.app / "key.pdf", 999)
    put(e.outside / "x.pdf", 1)
    e.put = put
    e.policy = PathPolicy(SecurityConfig(allowed_roots=(e.dl, e.docs, e.work),
                                         protected_paths=(e.app,), default_scope=e.dl))
    return e


def names(res):
    return [i.name for i in res.items]


def PDFS(env, **kw):
    return scan(env.dl, recursive=True, file_types=["pdf"],
                is_protected=env.policy.is_protected, **kw)


# ----------------------------------------------------------------------- scan
def test_scan_recursive_by_type(env):
    assert names(PDFS(env)) == ["a.pdf", "b.pdf", "c.pdf"]


def test_scan_name_matching(env):
    r = scan(env.dl, recursive=True, names=["NOTE"], is_protected=env.policy.is_protected)
    assert names(r) == ["notes.txt"]                       # part of the name, any case
    assert names(PDFS(env, filenames=["A.PDF"])) == ["a.pdf"]   # exact name, any case
    assert names(PDFS(env, filenames=["a"])) == []


def test_scan_date_filter_end_is_exclusive(env):
    df = {"start": "2026-10-01", "end": "2026-11-01", "field": "modified"}
    assert names(PDFS(env, date_filter=df)) == ["b.pdf", "c.pdf"]
    df = {"start": None, "end": "2026-10-10", "field": "modified"}
    assert names(PDFS(env, date_filter=df)) == ["a.pdf"]


def test_list_is_not_recursive_and_includes_folders(env):
    r = scan(env.dl, recursive=False, is_protected=env.policy.is_protected)
    assert names(r) == ["a.pdf", "b.pdf", "notes.txt", "photo.jpg", "sub"]


def test_scan_skips_protected_folders(env):
    r = scan(env.work, recursive=True, file_types=["pdf"], is_protected=env.policy.is_protected)
    assert names(r) == ["w.pdf"]


def test_scan_truncates(env, monkeypatch):
    monkeypatch.setattr("backend.tools.filesystem.scan.MAX_RESULTS", 2)
    r = PDFS(env)
    assert len(r.items) == 2 and r.truncated is True


def test_scan_does_not_follow_symlinks(env):
    try:
        os.symlink(env.outside, env.dl / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks aren't permitted here")
    assert "x.pdf" not in names(PDFS(env))


@pytest.mark.skipif(os.name != "nt", reason="junctions exist only on Windows")
def test_scan_does_not_follow_junctions(env):
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(env.dl / "junc"), str(env.outside)],
                          capture_output=True)
    if done.returncode != 0:
        pytest.skip("couldn't create a junction")
    assert "x.pdf" not in names(PDFS(env))


# ------------------------------------------------------------------ selection
def test_select_extremes(env):
    items = PDFS(env).items

    def pick(mode):
        return [i.name for i in select(items, False, mode, set())]

    assert pick("largest") == ["b.pdf"] and pick("smallest") == ["a.pdf"]
    assert pick("newest") == ["c.pdf"] and pick("oldest") == ["a.pdf"]
    assert pick("all") == ["a.pdf", "b.pdf", "c.pdf"]


def test_select_remaining_skips_what_was_taken(env):
    items = PDFS(env).items
    got = select(items, False, "remaining", {norm(env.dl / "b.pdf")})
    assert [i.name for i in got] == ["a.pdf", "c.pdf"]
    with pytest.raises(SelectionError):
        select(items, False, "remaining", {norm(i.path) for i in items})


def test_select_refuses_ties_empty_truncated_and_ambiguous(env):
    env.put(env.dl / "d.pdf", 100)
    with pytest.raises(SelectionError, match="tie"):
        select(PDFS(env).items, False, "largest", set())
    with pytest.raises(SelectionError, match="No files"):
        select([], False, "all", set())
    with pytest.raises(SelectionError, match="Too many"):
        select(PDFS(env).items, True, "all", set())
    with pytest.raises(SelectionError, match="exactly one"):
        select(PDFS(env).items, False, "only", set())
    assert [i.name for i in select(PDFS(env, filenames=["a.pdf"]).items, False, "only", set())] == ["a.pdf"]


def test_select_size_needs_files_not_folders(env):
    r = scan(env.dl, recursive=False, names=["sub"], is_protected=env.policy.is_protected)
    with pytest.raises(SelectionError, match="Only folders"):
        select(r.items, False, "largest", set())


# -------------------------------------------------------------------- prepare
def T(tid, action, params, deps=(), approval=None):
    risk = BASE_RISK[action]
    needs = risk in APPROVAL_RISKS if approval is None else approval
    return Task(task_id=tid, action=action, parameters=params, dependencies=list(deps),
                risk_level=risk, approval_required=needs)


def plan(*tasks):
    return ExecutionPlan(plan_id="p", request_id="r", tasks=list(tasks))


def search(env, **over):
    params = {"filenames": [], "names": [], "file_types": ["pdf"], "date_filter": None,
              "scope": {"path": str(env.dl)}}
    params.update(over)
    return T("t1", "search_files", params)


def flow(env):
    return plan(
        search(env),
        T("t2", "open_file", {"target": {"from_task": "t1", "select": "largest"}},
          ["t1"], approval=True),
        T("t3", "move_file",
          {"targets": [{"from_task": "t1", "select": "remaining", "except_tasks": ["t2"]}],
           "destination": "Archive"}, ["t1", "t2"]))


def test_find_open_largest_move_rest(env):
    p = prepare(flow(env), env.policy)
    assert p.ok and p.needs_approval and p.digest
    assert [(o.task_id, o.action, Path(o.source).name) for o in p.operations] == [
        ("t2", "open_file", "b.pdf"), ("t3", "move_file", "a.pdf"), ("t3", "move_file", "c.pdf")]
    assert Path(p.operations[1].destination) == env.docs / "Archive" / "a.pdf"
    assert p.reads[0].count == 3
    assert "Move" in p.summary()


def test_digest_is_stable_and_tracks_the_files(env):
    pl = flow(env)
    first = prepare(pl, env.policy).digest
    assert prepare(pl, env.policy).digest == first
    env.put(env.dl / "z.pdf", 200)                      # a new largest file
    assert prepare(pl, env.policy).digest != first


def test_delete_explicit_file(env):
    p = prepare(plan(T("t1", "move_to_recycle_bin",
                       {"targets": [{"path": str(env.dl / "photo.jpg")}]})), env.policy)
    assert p.ok and p.needs_approval and p.operations[0].risk == "destructive"


def test_created_file_can_be_edited_in_the_same_plan(env):
    p = prepare(plan(
        T("t1", "create_text_file", {"name": "todo.txt"}),
        T("t2", "edit_text_file",
          {"target": {"from_task": "t1", "select": "created"},
           "operation": "append", "text": "buy milk"}, ["t1"], approval=True)), env.policy)
    assert p.ok
    assert [o.action for o in p.operations] == ["create_text_file", "edit_text_file"]
    assert p.operations[1].source == p.operations[0].destination == str(env.dl / "todo.txt")


def test_no_match_blocks_the_plan(env):
    p = prepare(plan(
        search(env, names=["zzz"], file_types=[]),
        T("t2", "open_file", {"target": {"from_task": "t1", "select": "largest"}},
          ["t1"], approval=True)), env.policy)
    assert not p.ok and p.operations == [] and p.digest == ""
    assert any("No files matched" in x for x in p.problems)


def test_tie_blocks_the_plan(env):
    env.put(env.dl / "d.pdf", 100)
    p = prepare(flow(env), env.policy)
    assert not p.ok and any("tie" in x for x in p.problems)


def test_overwrite_conflict_blocks_the_plan(env):
    (env.docs / "Archive" / "a.pdf").write_bytes(b"1")
    p = prepare(flow(env), env.policy)
    assert not p.ok and any("already exists" in x for x in p.problems)


def test_search_after_a_change_is_refused(env):
    p = prepare(plan(
        T("t1", "create_folder", {"name": "Fresh"}),
        T("t2", "search_files", {"filenames": [], "names": [], "file_types": ["pdf"],
                                 "date_filter": None, "scope": None}, ["t1"])), env.policy)
    assert not p.ok and any("after a change" in x for x in p.problems)


def test_same_file_changed_twice_is_refused(env):
    a = {"path": str(env.dl / "a.pdf")}
    p = prepare(plan(T("t1", "move_file", {"targets": [a], "destination": "Archive"}),
                     T("t2", "move_to_recycle_bin", {"targets": [a]}, ["t1"])), env.policy)
    assert not p.ok and any("more than one step" in x for x in p.problems)


def test_two_files_to_the_same_destination_are_refused(env):
    env.put(env.dl / "sub" / "a.pdf", 4)
    targets = [{"path": str(env.dl / "a.pdf")}, {"path": str(env.dl / "sub" / "a.pdf")}]
    p = prepare(plan(T("t1", "move_file", {"targets": targets, "destination": "Archive"})),
                env.policy)
    assert not p.ok and any("more than one step" in x for x in p.problems)


def test_operation_limit(env, monkeypatch):
    monkeypatch.setattr("backend.execution.prepare.MAX_OPERATIONS", 2)
    p = prepare(flow(env), env.policy)
    assert not p.ok and any("Too many" in x for x in p.problems)


# ------------------------------------------------------------------- approval
def test_approval_roundtrip_and_detects_changes(env):
    pl = flow(env)
    ap = grant(prepare(pl, env.policy), now=1000.0)
    check(prepare(pl, env.policy), ap, now=1100.0)                  # nothing changed: fine
    env.put(env.dl / "z.pdf", 200)
    with pytest.raises(ApprovalError, match="changed"):
        check(prepare(pl, env.policy), ap, now=1100.0)


def test_approval_expires_and_must_match_the_plan(env):
    pl = flow(env)
    prepared = prepare(pl, env.policy)
    ap = grant(prepared, now=1000.0)
    with pytest.raises(ApprovalError, match="expired"):
        check(prepared, ap, now=1000.0 + 601)
    with pytest.raises(ApprovalError, match="different plan"):
        check(prepared, Approval("other", ap.digest, 1000.0), now=1001.0)


def test_approval_rules(env):
    needs = prepare(flow(env), env.policy)
    with pytest.raises(ApprovalError, match="approval"):
        check(needs, None)
    read_only = prepare(plan(search(env)), env.policy)
    assert not read_only.needs_approval
    check(read_only, None)                                          # reading needs no approval
    bad = prepare(plan(search(env, names=["zzz"], file_types=[]),
                       T("t2", "open_file", {"target": {"from_task": "t1", "select": "largest"}},
                         ["t1"], approval=True)), env.policy)
    with pytest.raises(ApprovalError):
        grant(bad)