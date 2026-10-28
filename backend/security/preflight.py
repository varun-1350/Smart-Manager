from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.planner.validator import validate_plan
from backend.schemas.plan import ExecutionPlan
from backend.schemas.task import Task

from .errors import SecurityError
from .pathutil import DRIVE_ABS, check_plain_name, is_within, norm, same_path
from .paths import PathPolicy

MUTATING = frozenset({"move_to_recycle_bin", "move_file", "rename_file", "edit_text_file"})
_BAD_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")   # control characters (not \n \r \t)


@dataclass
class TaskCheck:
    task_id: str
    action: str
    paths: list[str] = field(default_factory=list)   # concrete paths known right now
    destination: str | None = None
    deferred: bool = False                           # some targets come from earlier tasks
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)   # would overwrite something: blocks approval

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass
class PreflightReport:
    plan_id: str
    tasks: list[TaskCheck]

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.tasks)

    def problems(self) -> list[str]:
        return [f"{t.task_id} ({t.action}): {p}" for t in self.tasks for p in t.problems]


# ------------------------------------------------------------ per-path rules
def action_rules(policy: PathPolicy, action: str, path: Path) -> list[str]:
    cfg, ext, problems = policy.config, path.suffix.lower(), []
    if action == "open_file" and path.is_file() and ext in cfg.blocked_extensions:
        problems.append(f"'{path.name}' is a program or script type ({ext}). I won't open it.")
    if action == "edit_text_file":
        if not path.is_file():
            problems.append(f"'{path.name}' isn't a file.")
        elif ext not in cfg.editable_extensions:
            allowed = ", ".join(sorted(cfg.editable_extensions))
            problems.append(f"I can only edit {allowed} files, not '{path.name}'.")
    return problems


def check_resolved(policy: PathPolicy, action: str, path) -> list[str]:
    """Problems with acting on ONE concrete path. The executor must call this for every
    file a reference resolves to, and again right before changing anything."""
    try:
        real = policy.check(path, mutating=action in MUTATING, must_exist=True)
    except SecurityError as exc:
        return [str(exc)]
    return action_rules(policy, action, real)


# -------------------------------------------------------------- plan helpers
def _items(task: Task) -> list:
    p = task.parameters
    if "targets" in p:
        return p["targets"]
    return [p["target"]] if "target" in p else []


def _folder_spec(text: str) -> dict:
    return {"path": text} if (DRIVE_ABS.match(text) or "/" in text or "\\" in text) \
        else {"name": text}


def _resolve_targets(task: Task, c: TaskCheck, policy: PathPolicy,
                     concrete: dict[str, list[Path]]) -> list[Path]:
    mutating = task.action in MUTATING
    out: list[Path] = []
    for item in _items(task):
        found: list[Path] = []
        if "from_task" in item:
            picked = concrete.get(task.task_id)
            if picked is None:
                c.deferred = True       # decided at run time; checked via check_resolved
                continue
            for raw in picked:
                try:
                    found.append(policy.check(raw, mutating=mutating, must_exist=True))
                except SecurityError as exc:
                    c.problems.append(str(exc))
        else:
            try:
                found.append(policy.resolve_existing(item, mutating=mutating))
            except SecurityError as exc:
                c.problems.append(str(exc))
        for path in found:
            c.problems += action_rules(policy, task.action, path)
            c.paths.append(str(path))
            out.append(path)
    return out


def _check_task(task: Task, c: TaskCheck, policy: PathPolicy, planned: dict[str, Path],
                concrete: dict[str, list[Path]]) -> None:
    a, p, cfg = task.action, task.parameters, policy.config

    if a in ("search_files", "list_files"):
        c.paths.append(str(policy.resolve_folder(p["scope"], planned)))
        return

    if a in ("create_folder", "create_text_file"):
        path = policy.resolve_new(p, planned)
        if a == "create_text_file" and path.suffix.lower() not in cfg.editable_extensions:
            allowed = ", ".join(sorted(cfg.editable_extensions))
            c.problems.append(f"Text files must end in one of: {allowed}.")
        c.paths.append(str(path))
        if a == "create_folder":
            if norm(path) in planned:
                c.problems.append(f"'{path.name}' is created twice in this plan.")
            planned[norm(path)] = path
        return

    targets = _resolve_targets(task, c, policy, concrete)

    if a == "edit_text_file":
        for key in ("text", "old_text", "new_text"):
            if key in p and (len(p[key]) > cfg.max_edit_chars or _BAD_TEXT.search(p[key])):
                c.problems.append(f"The '{key}' is too long or contains control characters.")

    elif a == "move_file":
        dest = policy.resolve_folder(_folder_spec(p["destination"]), planned)
        c.destination = str(dest)
        for t in targets:
            if t.is_dir() and is_within(dest, t):
                c.problems.append(f"Can't move '{t.name}' into itself.")
            elif same_path(t.parent, dest):
                c.warnings.append(f"'{t.name}' is already in that folder.")
            elif (dest / t.name).exists():
                msg = f"'{t.name}' already exists in '{dest}'."
                c.warnings.append(msg + " This needs a decision before it runs.")
                c.conflicts.append(msg)

    elif a == "rename_file":
        new = check_plain_name(p["new_name"], "new name")
        if Path(new).suffix.lower() in cfg.blocked_extensions:
            c.problems.append("I won't rename a file into a program or script type.")
        for t in targets:
            new_path = policy.check(t.parent / new, mutating=True)
            if new_path.exists() and not same_path(new_path, t):
                c.problems.append(f"'{new}' already exists in that folder.")
            c.destination = str(new_path)


def preflight(plan: ExecutionPlan, policy: PathPolicy,
              concrete: dict[str, list[Path]] | None = None) -> PreflightReport:
    """Check every task against the path and action rules. Never changes anything.
    `concrete` maps task_id -> the real files its reference resolved to (from a search).
    Without it, those targets stay deferred. Raises PlanningError if the plan is malformed."""
    concrete = concrete or {}
    order = validate_plan(plan)
    by_id = {t.task_id: t for t in plan.tasks}
    planned: dict[str, Path] = {}          # folders that earlier tasks will create
    checks: list[TaskCheck] = []
    for tid in order:
        task = by_id[tid]
        c = TaskCheck(task.task_id, task.action)
        try:
            _check_task(task, c, policy, planned, concrete)
        except SecurityError as exc:
            c.problems.append(str(exc))
        checks.append(c)
    return PreflightReport(plan.plan_id, checks)
    """Check every task against the path and action rules. Never changes anything.
    Raises PlanningError if the plan itself is malformed."""
    order = validate_plan(plan)
    by_id = {t.task_id: t for t in plan.tasks}
    planned: dict[str, Path] = {}          # folders that earlier tasks will create
    checks: list[TaskCheck] = []
    for tid in order:
        task = by_id[tid]
        c = TaskCheck(task.task_id, task.action)
        try:
            _check_task(task, c, policy, planned)
        except SecurityError as exc:
            c.problems.append(str(exc))
        checks.append(c)
    return PreflightReport(plan.plan_id, checks)