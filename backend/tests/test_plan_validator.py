import pytest

from backend.planner.errors import PlanningError
from backend.planner.validator import execution_order, validate_plan
from backend.schemas.plan import ExecutionPlan
from backend.schemas.task import RiskLevel, Task

SEARCH = {"filenames": [], "names": [], "file_types": ["pdf"], "date_filter": None}
REF = {"from_task": "t1", "select": "largest"}


def task(tid, action, params, deps=(), risk=RiskLevel.LOW, approval=False):
    return Task(task_id=tid, action=action, parameters=params, dependencies=list(deps),
                risk_level=risk, approval_required=approval)


def plan(*tasks):
    return ExecutionPlan(plan_id="p", request_id="r", tasks=list(tasks))


def t1():
    return task("t1", "search_files", SEARCH)


def t2_open(ref=REF, deps=("t1",)):
    return task("t2", "open_file", {"target": ref}, deps, RiskLevel.MEDIUM, True)


def test_valid_plan_returns_order():
    assert validate_plan(plan(t1(), t2_open())) == ["t1", "t2"]


def test_order_follows_dependencies_not_list_position():
    assert execution_order([t2_open(), t1()]) == ["t1", "t2"]


def test_cycle_is_rejected():
    a = task("t1", "search_files", SEARCH, ["t2"])
    b = task("t2", "search_files", SEARCH, ["t1"])
    with pytest.raises(PlanningError, match="cycle"):
        validate_plan(plan(a, b))


@pytest.mark.parametrize("bad", [
    plan(t1(), task("t1", "search_files", SEARCH)),                       # duplicate id
    plan(task("t1", "search_files", SEARCH, ["t1"])),                     # self dependency
    plan(task("t1", "search_files", SEARCH, ["t9"])),                     # missing dependency
    plan(task("t1", "run_shell", {"cmd": "del *"})),                      # unknown action
    plan(*[task(f"t{i}", "search_files", SEARCH) for i in range(21)]),    # too many tasks
])
def test_structural_problems_rejected(bad):
    with pytest.raises(PlanningError):
        validate_plan(bad)


def test_unexpected_parameters_rejected():
    bad = task("t1", "open_file", {"target": {"filename": "a.txt"}, "shell": "rm -rf"},
               risk=RiskLevel.MEDIUM)
    with pytest.raises(PlanningError):
        validate_plan(plan(bad))


def test_risk_cannot_be_downgraded():
    bad = task("t1", "move_to_recycle_bin", {"targets": [{"filename": "a.txt"}]},
               risk=RiskLevel.LOW)
    with pytest.raises(PlanningError):
        validate_plan(plan(bad))


def test_high_risk_requires_approval():
    bad = task("t1", "move_file", {"targets": [{"filename": "a.txt"}], "destination": "X"},
               risk=RiskLevel.HIGH, approval=False)
    with pytest.raises(PlanningError):
        validate_plan(plan(bad))


def test_reference_requires_approval():
    bad = task("t2", "open_file", {"target": REF}, ["t1"], RiskLevel.MEDIUM, False)
    with pytest.raises(PlanningError):
        validate_plan(plan(t1(), bad))


@pytest.mark.parametrize("ref, deps", [
    ({"from_task": "t1", "select": "largest"}, []),                          # not a dependency
    ({"from_task": "t9", "select": "largest"}, ["t1"]),                      # unknown source
    ({"from_task": "t1", "select": "biggest-ish"}, ["t1"]),                  # unknown selection
    ({"from_task": "t1", "select": "all"}, ["t1"]),                          # many files, one-file action
    ({"from_task": "t1", "select": "largest", "x": 1}, ["t1"]),              # extra key
    ({"from_task": "t1", "select": "created"}, ["t1"]),                      # t1 is a search
])
def test_bad_references_rejected(ref, deps):
    with pytest.raises(PlanningError):
        validate_plan(plan(t1(), t2_open(ref, deps)))


def test_remaining_needs_except_tasks():
    bad = task("t3", "move_file",
               {"targets": [{"from_task": "t1", "select": "remaining"}], "destination": "A"},
               ["t1"], RiskLevel.HIGH, True)
    with pytest.raises(PlanningError):
        validate_plan(plan(t1(), bad))


def test_reference_cannot_hide_in_another_parameter():
    bad = task("t2", "move_file",
               {"targets": [{"filename": "a.txt"}], "destination": REF},
               ["t1"], RiskLevel.HIGH, True)
    with pytest.raises(PlanningError):
        validate_plan(plan(t1(), bad))


def test_created_reference_to_a_folder_cannot_be_edited():
    folder = task("t1", "create_folder", {"name": "Notes"}, risk=RiskLevel.MEDIUM)
    edit = task("t2", "edit_text_file",
                {"target": {"from_task": "t1", "select": "created"},
                 "operation": "append", "text": "x"},
                ["t1"], RiskLevel.HIGH, True)
    with pytest.raises(PlanningError):
        validate_plan(plan(folder, edit))


def test_bad_date_filter_rejected():
    bad = task("t1", "search_files", {**SEARCH, "date_filter": {
        "text": "x", "start": "2026-10-10", "end": "2026-10-01", "field": "modified"}})
    with pytest.raises(PlanningError):
        validate_plan(plan(bad))