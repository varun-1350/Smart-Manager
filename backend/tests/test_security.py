import json
import os
import subprocess
from pathlib import Path

import pytest

from backend.planner.actions import APPROVAL_RISKS
from backend.planner.errors import PlanningError
from backend.planner.validator import BASE_RISK
from backend.schemas.plan import ExecutionPlan
from backend.schemas.task import Task
from backend.security.config import SecurityConfig, default_config, load_config
from backend.security.errors import SecurityError
from backend.security.pathutil import check_absolute_text, check_plain_name
from backend.security.paths import PathPolicy
from backend.security.preflight import check_resolved, preflight

SEARCH = {"filenames": [], "names": [], "file_types": ["pdf"], "date_filter": None, "scope": None}


class Env:
    pass


@pytest.fixture
def env(tmp_path):
    base = tmp_path.resolve()
    e = Env()
    e.dl, e.docs, e.work = base / "Downloads", base / "Documents", base / "Work"
    e.app = e.work / "Projects" / "App"          # protected
    e.outside = base / "Outside"                 # not an allowed root
    for d in (e.dl, e.docs, e.app, e.outside, e.dl / "sub"):
        d.mkdir(parents=True)
    for f in (e.dl / "report.pdf", e.dl / "notes.txt", e.dl / "setup.exe",
              e.docs / "notes.txt", e.app / "key.txt", e.outside / "x.txt"):
        f.write_text("data")
    cfg = SecurityConfig(allowed_roots=(e.dl, e.docs, e.work),
                         protected_paths=(e.app,), default_scope=e.dl)
    e.policy = PathPolicy(cfg)
    return e


def P(path):
    return {"path": str(path)}


def task(tid, action, params, deps=(), approval=None):
    risk = BASE_RISK[action]
    needs = risk in APPROVAL_RISKS if approval is None else approval
    return Task(task_id=tid, action=action, parameters=params, dependencies=list(deps),
                risk_level=risk, approval_required=needs)


def run(env, *tasks):
    return preflight(ExecutionPlan(plan_id="p", request_id="r", tasks=list(tasks)), env.policy)


# ------------------------------------------------------------------ text rules
@pytest.mark.parametrize("raw", [
    r"..\x", r"relative\a.txt", r"\\server\share\a.txt", r"\\?\C:\a.txt",
    r"D:\a\..\b.txt", r"D:\a.txt:stream", r"D:\CON", r"D:\nul.txt", "D:\\a.txt ",
    r"D:\a|b", r"D:\dir.\a", "",
])
def test_bad_absolute_paths_rejected(raw):
    with pytest.raises(SecurityError):
        check_absolute_text(raw)


def test_good_absolute_path_accepted():
    check_absolute_text(r"D:\Work\a.txt")
    check_absolute_text("D:/Work/a.txt")


@pytest.mark.parametrize("name", ["a\\b", "a/b", "..", "a:b", "", "con", "x.", "a*b", " "])
def test_bad_plain_names_rejected(name):
    with pytest.raises(SecurityError):
        check_plain_name(name)


# ---------------------------------------------------------------- containment
def test_file_in_allowed_root_ok(env):
    f = env.dl / "report.pdf"
    assert env.policy.resolve_existing(P(f), mutating=True) == f


def test_outside_and_protected_denied(env):
    for bad in (env.outside / "x.txt", env.app / "key.txt"):
        for mutating in (False, True):
            with pytest.raises(SecurityError):
                env.policy.resolve_existing(P(bad), mutating=mutating)


def test_cannot_change_a_folder_that_contains_protected(env):
    with pytest.raises(SecurityError):
        env.policy.check(env.work / "Projects", mutating=True, must_exist=True)
    env.policy.check(env.work / "Projects", mutating=False, must_exist=True)   # listing is fine


def test_cannot_change_an_allowed_folder_itself(env):
    with pytest.raises(SecurityError):
        env.policy.check(env.dl, mutating=True, must_exist=True)
    env.policy.check(env.dl, mutating=False, must_exist=True)


def test_dotdot_traversal_rejected(env):
    with pytest.raises(SecurityError):
        env.policy.resolve_existing(P(f"{env.dl}\\..\\Outside\\x.txt"), mutating=False)


# -------------------------------------------------------------- name lookups
def test_bare_name_unique(env):
    assert env.policy.resolve_existing({"filename": "report.pdf"}, mutating=False) == env.dl / "report.pdf"


def test_bare_name_ambiguous_missing_or_a_path(env):
    with pytest.raises(SecurityError, match="more than one"):
        env.policy.resolve_existing({"filename": "notes.txt"}, mutating=False)
    with pytest.raises(SecurityError, match="can't find"):
        env.policy.resolve_existing({"filename": "nothing.txt"}, mutating=False)
    with pytest.raises(SecurityError):
        env.policy.resolve_existing({"filename": r"..\Outside\x.txt"}, mutating=False)


def test_folder_resolution(env):
    assert env.policy.resolve_folder(None) == env.dl
    assert env.policy.resolve_folder({"name": "Documents"}) == env.docs
    assert env.policy.resolve_folder({"name": "sub"}) == env.dl / "sub"
    for bad in ({"name": "Nope"}, P(env.dl / "report.pdf"), P(env.outside)):
        with pytest.raises(SecurityError):
            env.policy.resolve_folder(bad)


def test_resolve_new(env):
    assert env.policy.resolve_new({"name": "fresh.txt"}) == env.dl / "fresh.txt"
    assert env.policy.resolve_new({"name": "fresh", "parent": {"name": "Documents"}}) == env.docs / "fresh"
    for bad in ({"name": "report.pdf"},                        # already exists
                {"name": r"..\x"},                             # traversal
                {"name": "a", "parent": P(env.outside)},       # outside
                {"path": str(env.outside / "n.txt")},
                {"name": "k.txt", "parent": P(env.app)}):      # protected
        with pytest.raises(SecurityError):
            env.policy.resolve_new(bad)


# ------------------------------------------------------------- links/junctions
def test_symlink_rejected(env):
    link = env.dl / "link"
    try:
        os.symlink(env.outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks aren't permitted here")
    with pytest.raises(SecurityError):
        env.policy.resolve_existing(P(link / "x.txt"), mutating=False)


@pytest.mark.skipif(os.name != "nt", reason="junctions exist only on Windows")
def test_junction_rejected(env):
    link = env.dl / "junc"
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(env.outside)],
                          capture_output=True)
    if done.returncode != 0:
        pytest.skip("couldn't create a junction")
    with pytest.raises(SecurityError):
        env.policy.resolve_existing(P(link / "x.txt"), mutating=False)
    with pytest.raises(SecurityError):
        env.policy.resolve_new({"name": "evil.txt", "parent": P(link)})


# ----------------------------------------------------------------------- config
def test_default_config(tmp_path):
    cfg = default_config(home=tmp_path, project_root=tmp_path / "proj")
    assert {"Desktop", "Documents", "Downloads"} <= {p.name for p in cfg.allowed_roots}
    assert tmp_path / "proj" in cfg.protected_paths
    assert cfg.default_scope == tmp_path / "Downloads"


def test_extra_roots(tmp_path):
    ok = default_config(home=tmp_path, project_root=tmp_path / "proj",
                        extra_roots=[tmp_path / "Work"])
    assert tmp_path / "Work" in ok.allowed_roots
    for bad in (tmp_path / "proj" / "data", Path(tmp_path.anchor), "relative"):
        with pytest.raises(SecurityError):
            default_config(home=tmp_path, project_root=tmp_path / "proj", extra_roots=[bad])


def test_load_config(tmp_path):
    f = tmp_path / "security.json"
    f.write_text(json.dumps({"allowed_roots": [str(tmp_path / "Work")]}))
    assert tmp_path / "Work" in load_config(f, home=tmp_path).allowed_roots
    f.write_text("{not json")
    with pytest.raises(SecurityError):
        load_config(f, home=tmp_path)
    assert load_config(tmp_path / "missing.json", home=tmp_path).allowed_roots


# -------------------------------------------------------------------- preflight
def test_open_rules(env):
    r = run(env, task("t1", "open_file", {"target": P(env.dl / "report.pdf")}))
    assert r.ok and r.tasks[0].paths == [str(env.dl / "report.pdf")]
    r = run(env, task("t1", "open_file", {"target": P(env.dl / "setup.exe")}))
    assert not r.ok and "program or script" in r.tasks[0].problems[0]


def test_delete_rules(env):
    assert run(env, task("t1", "move_to_recycle_bin", {"targets": [P(env.dl / "report.pdf")]})).ok
    for bad in (env.dl, env.outside / "x.txt", env.app / "key.txt", env.work / "Projects"):
        assert not run(env, task("t1", "move_to_recycle_bin", {"targets": [P(bad)]})).ok


def test_one_bad_target_blocks_only_itself_but_fails_the_task(env):
    r = run(env, task("t1", "move_to_recycle_bin",
                      {"targets": [P(env.dl / "report.pdf"), P(env.outside / "x.txt")]}))
    c = r.tasks[0]
    assert not r.ok and len(c.problems) == 1 and c.paths == [str(env.dl / "report.pdf")]


def test_move_rules(env):
    src = P(env.dl / "notes.txt")
    r = run(env, task("t1", "move_file", {"targets": [src], "destination": "Documents"}))
    assert r.ok and any("already exists" in w for w in r.tasks[0].warnings)
    r = run(env, task("t1", "move_file", {"targets": [P(env.dl / "report.pdf")], "destination": "Documents"}))
    assert r.ok and r.tasks[0].warnings == [] and r.tasks[0].destination == str(env.docs)
    for dest in ("Nowhere", str(env.outside)):
        assert not run(env, task("t1", "move_file", {"targets": [src], "destination": dest})).ok
    sub = P(env.dl / "sub")
    assert not run(env, task("t1", "move_file", {"targets": [sub], "destination": str(env.dl / "sub")})).ok


def test_rename_rules(env):
    f = P(env.dl / "report.pdf")
    r = run(env, task("t1", "rename_file", {"target": f, "new_name": "final.pdf"}))
    assert r.ok and r.tasks[0].destination == str(env.dl / "final.pdf")
    assert not run(env, task("t1", "rename_file", {"target": f, "new_name": "notes.txt"})).ok
    assert not run(env, task("t1", "rename_file", {"target": f, "new_name": "report.exe"})).ok


def test_edit_rules(env):
    ok = {"target": P(env.dl / "notes.txt"), "operation": "append", "text": "hi"}
    assert run(env, task("t1", "edit_text_file", ok)).ok
    assert not run(env, task("t1", "edit_text_file", {**ok, "target": P(env.dl / "report.pdf")})).ok
    assert not run(env, task("t1", "edit_text_file", {**ok, "text": "x" * 10_001})).ok
    assert not run(env, task("t1", "edit_text_file", {**ok, "text": "a\x00b"})).ok


def test_create_rules(env):
    r = run(env, task("t1", "create_folder", {"name": "Archive"}))
    assert r.ok and r.tasks[0].paths == [str(env.dl / "Archive")]
    assert not run(env, task("t1", "create_folder", {"name": "sub"})).ok                 # exists
    assert run(env, task("t1", "create_text_file", {"name": "todo.txt"})).ok
    assert not run(env, task("t1", "create_text_file", {"name": "tool.exe"})).ok
    assert not run(env, task("t1", "create_folder", {"name": "A", "parent": P(env.outside)})).ok


def test_folder_created_earlier_in_the_plan_can_be_used(env):
    r = run(env,
            task("t1", "create_folder", {"name": "Archive"}),
            task("t2", "move_file", {"targets": [P(env.dl / "report.pdf")],
                                     "destination": "Archive"}, ["t1"]))
    assert r.ok and r.tasks[1].destination == str(env.dl / "Archive")


def test_same_folder_created_twice_is_a_problem(env):
    r = run(env, task("t1", "create_folder", {"name": "Archive"}),
            task("t2", "create_folder", {"name": "Archive"}, ["t1"]))
    assert not r.ok


def test_references_are_deferred_not_guessed(env):
    r = run(env,
            task("t1", "search_files", SEARCH),
            task("t2", "open_file", {"target": {"from_task": "t1", "select": "largest"}},
                 ["t1"], approval=True))
    assert r.ok and r.tasks[1].deferred and r.tasks[1].paths == []
    assert r.tasks[0].paths == [str(env.dl)]


def test_check_resolved_for_reference_results(env):
    assert check_resolved(env.policy, "open_file", env.dl / "report.pdf") == []
    assert check_resolved(env.policy, "open_file", env.dl / "setup.exe")
    assert check_resolved(env.policy, "move_file", env.outside / "x.txt")
    assert check_resolved(env.policy, "edit_text_file", env.dl / "report.pdf")
    assert check_resolved(env.policy, "move_to_recycle_bin", env.dl / "gone.txt")


def test_malformed_plan_is_rejected_before_any_path_check(env):
    bad = Task(task_id="t1", action="run_shell", parameters={})
    with pytest.raises(PlanningError):
        preflight(ExecutionPlan(plan_id="p", request_id="r", tasks=[bad]), env.policy)