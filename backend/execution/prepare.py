from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.planner.validator import validate_plan
from backend.schemas.plan import ExecutionPlan
from backend.schemas.task import Task
from backend.security.errors import SecurityError
from backend.security.pathutil import norm
from backend.security.paths import PathPolicy
from backend.security.preflight import preflight
from backend.tools.filesystem.scan import ScanResult, scan

from .selection import SelectionError, select

READ_ONLY = frozenset({"search_files", "list_files"})
CREATORS = frozenset({"create_folder", "create_text_file"})
STATE_CHANGING = frozenset({"create_folder", "create_text_file", "move_file",
                            "rename_file", "edit_text_file", "move_to_recycle_bin"})
MAX_OPERATIONS = 200
SAMPLE = 20


def _clip(text: str, n: int = 60) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= n else flat[: n - 3] + "..."


@dataclass(frozen=True)
class Operation:
    """One concrete thing the executor would do to one real path."""
    task_id: str
    action: str
    source: str | None
    destination: str | None
    detail: dict
    risk: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)

    def describe(self) -> str:
        a, s, d = self.action, self.source, self.destination
        if a == "open_file":
            return f"Open {s}"
        if a == "copy_path_to_clipboard":
            return f"Copy the path of {s} to the clipboard"
        if a == "move_to_recycle_bin":
            return f"Move {s} to the Recycle Bin"
        if a == "move_file":
            return f"Move {s} -> {d}"
        if a == "rename_file":
            return f"Rename {s} -> {d}"
        if a == "edit_text_file":
            if self.detail.get("operation") == "append":
                text = self.detail["text"]
                return f"Append {len(text)} characters to {s}: '{_clip(text)}'"
            return (f"In {s}, replace '{_clip(self.detail['old_text'])}' "
                    f"with '{_clip(self.detail['new_text'])}'")
        if a == "create_folder":
            return f"Create folder {d}"
        if a == "create_text_file":
            return f"Create text file {d}"
        return f"{a} {s or d}"


@dataclass
class ReadSummary:
    task_id: str
    action: str
    scope: str
    count: int
    truncated: bool
    sample: list[str]


@dataclass
class Prepared:
    plan_id: str
    operations: list[Operation]
    reads: list[ReadSummary]
    problems: list[str]
    needs_approval: bool
    digest: str                     # "" when there are problems: nothing can be approved

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        lines: list[str] = []
        for r in self.reads:
            more = " (stopped early: too many matches)" if r.truncated else ""
            lines.append(f"{r.task_id}: found {r.count} item(s) in {r.scope}{more}")
            lines += [f"    {s}" for s in r.sample]
            if r.count > len(r.sample):
                lines.append(f"    ... and {r.count - len(r.sample)} more")
        if self.operations:
            lines.append(f"Planned changes ({len(self.operations)}):")
            for o in self.operations:
                lines.append(f"  [{o.risk.upper()}] {o.describe()}")
                lines += [f"      note: {w}" for w in o.warnings]
        if self.problems:
            lines.append("Problems:")
            lines += [f"  - {p}" for p in self.problems]
        return "\n".join(lines)


def _plan_dict(plan: ExecutionPlan) -> dict:
    if hasattr(plan, "model_dump"):
        return plan.model_dump(mode="json")
    return json.loads(plan.json())


def compute_digest(plan: ExecutionPlan, operations: list[Operation]) -> str:
    payload = {"v": 1, "plan": _plan_dict(plan), "operations": [o.to_dict() for o in operations]}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _items(task: Task) -> list:
    p = task.parameters
    if "targets" in p:
        return p["targets"]
    return [p["target"]] if "target" in p else []


def _operations(order, by_id, checks, created) -> list[Operation]:
    ops: list[Operation] = []
    for tid in order:
        task, c = by_id[tid], checks[tid]
        if task.action in READ_ONLY:
            continue
        p, risk = task.parameters, task.risk_level.value
        warns = tuple(w for w in c.warnings if w not in c.conflicts)

        def add(source, destination=None, detail=None):
            ops.append(Operation(tid, task.action, source, destination, detail or {}, risk, warns))

        if task.action in CREATORS:
            add(None, c.paths[0])
            continue
        sources = list(c.paths)
        for item in _items(task):
            if "from_task" in item and item["select"] == "created":
                sources.append(str(created[item["from_task"]]))   # exists only after its task runs
        for src in sources:
            if task.action == "move_file":
                add(src, str(Path(c.destination) / Path(src).name))
            elif task.action == "rename_file":
                add(src, str(Path(src).parent / p["new_name"]))
            elif task.action == "edit_text_file":
                add(src, None, {k: p[k] for k in ("operation", "text", "old_text", "new_text")
                                if k in p})
            else:
                add(src)
    return ops


def _collisions(ops: list[Operation]) -> list[str]:
    out: list[str] = []
    touched: dict[str, list[Operation]] = {}
    for o in ops:
        if o.action in STATE_CHANGING and o.source:
            touched.setdefault(norm(o.source), []).append(o)
    for group in touched.values():
        if len(group) > 1 and any(g.action != "edit_text_file" for g in group):
            ids = ", ".join(g.task_id for g in group)
            out.append(f"'{group[0].source}' would be changed by more than one step ({ids}).")
    produced: dict[str, Operation] = {}
    for o in ops:
        if o.destination and o.action in STATE_CHANGING:
            key = norm(o.destination)
            if key in produced:
                out.append(f"'{o.destination}' would be produced by more than one step "
                           f"({produced[key].task_id}, {o.task_id}).")
            produced[key] = o
    return out


def prepare(plan: ExecutionPlan, policy: PathPolicy) -> Prepared:
    """Phase 1. Runs only read-only tasks (search/list). Resolves references to real files,
    applies the security rules to every one, and returns the exact operations plus a digest.
    Changes nothing on disk. Raises PlanningError if the plan itself is malformed."""
    order = validate_plan(plan)
    by_id = {t.task_id: t for t in plan.tasks}
    problems: list[str] = []
    failed: set[str] = set()
    scans: dict[str, ScanResult] = {}
    reads: list[ReadSummary] = []
    concrete: dict[str, list[Path]] = {}      # task_id -> real files its reference resolved to
    chosen: dict[str, set[str]] = {}          # task_id -> normalized paths it picked
    created: dict[str, Path] = {}             # task_id -> path a create task will make
    planned: dict[str, Path] = {}
    changed = False                           # has an earlier task already changed things?

    for tid in order:
        task = by_id[tid]
        label = f"{tid} ({task.action})"
        broken = next((d for d in task.dependencies if d in failed), None)
        if broken:
            problems.append(f"{label}: can't go ahead because {broken} has a problem.")
            failed.add(tid)
            continue
        try:
            if task.action in READ_ONLY:
                if changed:
                    raise SecurityError("A search that comes after a change can't be previewed "
                                        "yet. Please make these separate requests.")
                p = task.parameters
                scope = policy.resolve_folder(p["scope"], planned)
                result = scan(scope, recursive=task.action == "search_files",
                              filenames=p.get("filenames", []), names=p.get("names", []),
                              file_types=p["file_types"], date_filter=p["date_filter"],
                              is_protected=policy.is_protected)
                scans[tid] = result
                reads.append(ReadSummary(tid, task.action, str(scope), len(result.items),
                                         result.truncated, [i.path for i in result.items[:SAMPLE]]))
            elif task.action in CREATORS:
                path = policy.resolve_new(task.parameters, planned)
                created[tid] = path
                if task.action == "create_folder":
                    planned[norm(path)] = path
                changed = True
            else:
                for item in _items(task):
                    if "from_task" not in item or item["select"] == "created":
                        continue
                    result = scans[item["from_task"]]
                    excluded: set[str] = set()
                    for other in item.get("except_tasks", []):
                        if other not in chosen:
                            raise SelectionError("'The rest' can only leave out files picked "
                                                 "from the same search.")
                        excluded |= chosen[other]
                    picked = select(result.items, result.truncated, item["select"], excluded)
                    concrete[tid] = [Path(i.path) for i in picked]
                    chosen[tid] = {norm(i.path) for i in picked}
                changed = changed or task.action in STATE_CHANGING
        except (SecurityError, SelectionError) as exc:
            problems.append(f"{label}: {exc}")
            failed.add(tid)

    # Second pass: the full security rules, now with real files instead of references.
    report = preflight(plan, policy, concrete=concrete)
    checks = {c.task_id: c for c in report.tasks}
    for c in report.tasks:
        problems += [f"{c.task_id} ({c.action}): {m}" for m in (*c.problems, *c.conflicts)]
    problems = list(dict.fromkeys(problems))

    operations: list[Operation] = []
    if not problems:
        operations = _operations(order, by_id, checks, created)
        problems += _collisions(operations)
        if len(operations) > MAX_OPERATIONS:
            problems.append(f"Too many operations ({len(operations)}). The limit is "
                            f"{MAX_OPERATIONS}. Please narrow the request.")
    if problems:
        operations = []
    digest = "" if problems else compute_digest(plan, operations)
    return Prepared(plan.plan_id, operations, reads, problems,
                    any(t.approval_required for t in plan.tasks), digest)