from __future__ import annotations
import re
from datetime import date

from backend.schemas.plan import ExecutionPlan
from backend.schemas.task import RiskLevel, Task

from .actions import ACTIONS, APPROVAL_RISKS, SUPPORTED_ACTIONS
from .errors import PlanningError
from .references import (MULTI_SELECTS, REFERENCE_ACTIONS, RESULT_PRODUCERS,
                         SINGLE_TARGET_ACTIONS)

MAX_TASKS = 20
CREATORS = frozenset({"create_folder", "create_text_file"})
SELECTS = frozenset({"largest", "smallest", "newest", "oldest",
                     "all", "remaining", "only", "created"})
TARGET_KEYS = frozenset({"path", "filename", "name"})
REF_KEYS = frozenset({"from_task", "select", "except_tasks"})

_RISK_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.DESTRUCTIVE]
BASE_RISK = {action: risk for action, risk in ACTIONS.values()}

_PARAMS = {
    "search_files": {"filenames", "names", "file_types", "date_filter", "scope"},
    "list_files": {"scope", "file_types", "date_filter"},
    "open_file": {"target"},
    "copy_path_to_clipboard": {"target"},
    "move_to_recycle_bin": {"targets"},
    "move_file": {"targets", "destination"},
    "rename_file": {"target", "new_name"},
}
_EDIT_PARAMS = {
    "append": {"target", "operation", "text"},
    "replace": {"target", "operation", "old_text", "new_text"},
}


def _fail(task: Task, msg: str) -> PlanningError:
    return PlanningError(f"Task {task.task_id} ({task.action}): {msg}")


def _has_ref(value) -> bool:
    if isinstance(value, dict):
        return "from_task" in value or any(_has_ref(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_ref(v) for v in value)
    return False


# ---------------------------------------------------------------- ordering
def execution_order(tasks: list[Task]) -> list[str]:
    """Dependency-respecting order (ties broken by original position).
    Raises on cycles. Dependencies must already be known to exist."""
    index = {t.task_id: i for i, t in enumerate(tasks)}
    waiting = {t.task_id: set(t.dependencies) for t in tasks}
    order: list[str] = []
    while waiting:
        ready = sorted((tid for tid, deps in waiting.items() if not deps), key=index.get)
        if not ready:
            raise PlanningError("The plan has a dependency cycle involving: "
                                + ", ".join(sorted(waiting)))
        order.append(ready[0])
        del waiting[ready[0]]
        for deps in waiting.values():
            deps.discard(ready[0])
    return order


# -------------------------------------------------------------- parameters
def _plain_str(task: Task, key: str, value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(task, f"'{key}' must be a non-empty text value.")
    return value


def _check_date_filter(task: Task, df) -> None:
    if df is None:
        return
    if not isinstance(df, dict) or set(df) - {"text", "start", "end", "field", "assumed_year"}:
        raise _fail(task, "date_filter has an unexpected shape.")
    if df.get("field") not in ("modified", "created"):
        raise _fail(task, "date_filter field must be 'modified' or 'created'.")
    start, end = df.get("start"), df.get("end")
    if start is None and end is None:
        raise _fail(task, "date_filter has no dates.")
    try:
        lo = date.fromisoformat(start) if start else None
        hi = date.fromisoformat(end) if end else None
    except (TypeError, ValueError):
        raise _fail(task, "date_filter dates must be ISO dates.") from None
    if lo and hi and lo >= hi:
        raise _fail(task, "date_filter start must be before its end.")


def _check_str_list(task: Task, key: str) -> list:
    value = task.parameters[key]
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise _fail(task, f"'{key}' must be a list of text values.")
    return value

def _check_scope(task: Task, key: str, value, allow_none: bool) -> None:
    if value is None and allow_none:
        return
    if not (isinstance(value, dict) and len(value) == 1 and set(value) <= {"path", "name"}
            and all(isinstance(v, str) and v.strip() for v in value.values())):
        raise _fail(task, f"'{key}' must be a folder name or path.")
    if ".." in re.split(r"[\\/]", next(iter(value.values()))):
        raise _fail(task, f"'{key}' can't contain '..'.")

def _check_params(task: Task) -> None:
    keys, p = set(task.parameters), task.parameters
    if task.action in CREATORS:
        if keys not in ({"name"}, {"path"}, {"name", "parent"}):
            raise _fail(task, "needs 'name' (optionally with 'parent') or 'path'.")
        key = "name" if "name" in keys else "path"
        value = _plain_str(task, key, p[key])
        if key == "name" and ("/" in value or "\\" in value):
            raise _fail(task, "'name' must be a plain name, not a path.")
        if "parent" in keys:
            _check_scope(task, "parent", p["parent"], allow_none=False)
        return
    if task.action == "edit_text_file":
        expected = _EDIT_PARAMS.get(p.get("operation"))
        if expected is None or keys != expected:
            raise _fail(task, "needs operation 'append' (text) or 'replace' (old_text, new_text).")
        for k in expected - {"target", "operation"}:
            if not isinstance(p[k], str):
                raise _fail(task, f"'{k}' must be text.")
        if p["operation"] == "replace" and not p["old_text"]:
            raise _fail(task, "'old_text' can't be empty.")
        return
    if keys != _PARAMS[task.action]:
        raise _fail(task, f"unexpected parameters: {sorted(keys)}.")

    if task.action == "search_files":
        lists = [_check_str_list(task, k) for k in ("filenames", "names", "file_types")]
        _check_date_filter(task, p["date_filter"])
        _check_scope(task, "scope", p["scope"], allow_none=True)
        if not any(lists) and p["date_filter"] is None:
            raise _fail(task, "has nothing to search for.")
    elif task.action == "list_files":
        _check_str_list(task, "file_types")
        _check_date_filter(task, p["date_filter"])
        _check_scope(task, "scope", p["scope"], allow_none=True)
    elif task.action == "move_file":
        _plain_str(task, "destination", p["destination"])
    elif task.action == "rename_file":
        name = _plain_str(task, "new_name", p["new_name"])
        if "/" in name or "\\" in name:
            raise _fail(task, "'new_name' must be a plain name, not a path.")


# -------------------------------------------------------------- references
def _target_items(task: Task) -> list:
    p = task.parameters
    if "target" in p:
        items = [p["target"]]
    elif "targets" in p:
        items = p["targets"]
    else:
        return []
    if not isinstance(items, list) or not items:
        raise _fail(task, "needs at least one target.")
    return items


def _check_references(task: Task, by_id: dict[str, Task]) -> bool:
    for key, value in task.parameters.items():       # a reference is only legal as a target
        if key not in ("target", "targets") and _has_ref(value):
            raise _fail(task, f"'{key}' can't point at another task.")
    items = _target_items(task)
    refs = [i for i in items if isinstance(i, dict) and "from_task" in i]

    if not refs:
        for item in items:
            if not (isinstance(item, dict) and len(item) == 1 and set(item) <= TARGET_KEYS
                    and all(isinstance(v, str) and v for v in item.values())):
                raise _fail(task, f"invalid target: {item!r}.")
        return False

    if task.action not in REFERENCE_ACTIONS:
        raise _fail(task, "can't use results of another task.")
    if len(items) != 1:
        raise _fail(task, "a reference must be the only target.")
    ref = refs[0]
    if set(ref) - REF_KEYS or "select" not in ref:
        raise _fail(task, "malformed reference.")
    select, source = ref["select"], by_id.get(ref["from_task"])
    if select not in SELECTS:
        raise _fail(task, f"unknown selection '{select}'.")
    if source is None or source.task_id not in task.dependencies:
        raise _fail(task, "a reference must point at a task it depends on.")

    if select == "created":
        if source.action not in CREATORS:
            raise _fail(task, "'created' must point at a create task.")
        if task.action == "edit_text_file" and source.action != "create_text_file":
            raise _fail(task, "a folder can't be edited as a text file.")
    elif source.action not in RESULT_PRODUCERS:
        raise _fail(task, f"'{select}' must point at a search or list task.")
    if task.action in SINGLE_TARGET_ACTIONS and select in MULTI_SELECTS:
        raise _fail(task, "works on one file, but this selects several.")

    excepted = ref.get("except_tasks", [])
    if select == "remaining":
        if not isinstance(excepted, list) or not excepted:
            raise _fail(task, "'remaining' must say what was already taken.")
    elif "except_tasks" in ref:
        raise _fail(task, "'except_tasks' only goes with 'remaining'.")
    for ex in excepted:
        if ex == source.task_id or ex not in by_id or ex not in task.dependencies:
            raise _fail(task, "'except_tasks' must be other tasks it depends on.")
    return True


# -------------------------------------------------------------------- risk
def _check_risk(task: Task, has_ref: bool) -> None:
    base = BASE_RISK[task.action]
    if _RISK_ORDER.index(task.risk_level) < _RISK_ORDER.index(base):
        raise _fail(task, f"risk can't be lower than '{base.value}'.")
    if task.risk_level in APPROVAL_RISKS and not task.approval_required:
        raise _fail(task, "high-risk tasks must require approval.")
    if has_ref and not task.approval_required:
        raise _fail(task, "tasks that act on earlier results must require approval.")


# -------------------------------------------------------------------- main
def validate_plan(plan: ExecutionPlan) -> list[str]:
    """Raise PlanningError if the plan is unsafe or malformed.
    Returns the order in which the executor must run the tasks."""
    tasks = plan.tasks
    if len(tasks) > MAX_TASKS:
        raise PlanningError(f"A plan can have at most {MAX_TASKS} tasks.")

    by_id: dict[str, Task] = {}
    for t in tasks:
        if not t.task_id.strip():
            raise PlanningError("A task has an empty id.")
        if t.task_id in by_id:
            raise PlanningError(f"Duplicate task id: {t.task_id}.")
        by_id[t.task_id] = t

    for t in tasks:
        if t.action not in SUPPORTED_ACTIONS:
            raise _fail(t, "unknown action.")
        if len(set(t.dependencies)) != len(t.dependencies):
            raise _fail(t, "lists a dependency twice.")
        for dep in t.dependencies:
            if dep == t.task_id:
                raise _fail(t, "depends on itself.")
            if dep not in by_id:
                raise _fail(t, f"depends on a task that doesn't exist: {dep}.")

    order = execution_order(tasks)          # raises on cycles
    for t in tasks:
        _check_params(t)
        _check_risk(t, _check_references(t, by_id))
    return order