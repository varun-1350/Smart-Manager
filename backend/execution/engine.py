from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.planner.validator import validate_plan
from backend.schemas.plan import ExecutionPlan, PlanStatus
from backend.schemas.result import TaskResult, VerificationStatus
from backend.security.errors import SecurityError
from backend.security.pathutil import same_path
from backend.security.paths import PathPolicy
from backend.security.preflight import check_resolved
from backend.tools.filesystem import files, system, textedit
from backend.tools.filesystem.common import ToolError, ToolResult

from .approval import Approval, ApprovalError  # noqa: F401  (ApprovalError re-exported)
from .approval import check as check_approval
from .journal import Journal, NullJournal
from .prepare import READ_ONLY, Operation, prepare
from .report import ExecutionReport, OperationOutcome


@dataclass
class Tools:
    """The tool functions the engine may call. Tests swap in fakes."""
    create_folder: Callable[..., ToolResult] = files.create_folder
    create_text_file: Callable[..., ToolResult] = files.create_text_file
    move_path: Callable[..., ToolResult] = files.move_path
    move_to_recycle_bin: Callable[..., ToolResult] = files.move_to_recycle_bin
    edit_text: Callable[..., ToolResult] = textedit.edit_text
    open_path: Callable[..., ToolResult] = system.open_path
    copy_path_to_clipboard: Callable[..., ToolResult] = system.copy_path_to_clipboard


def guard(policy: PathPolicy, op: Operation) -> list[str]:
    """Security re-check of ONE operation against the disk as it is right now.
    Runs immediately before every change. Returns problems; empty means go ahead."""
    cfg = policy.config
    problems: list[str] = []
    if op.source is not None:
        problems += check_resolved(policy, op.action, op.source)
    if op.destination is not None:
        dest = Path(op.destination)
        try:
            parent = policy.check(dest.parent, mutating=False, must_exist=True)
            if not parent.is_dir():
                problems.append(f"'{parent}' isn't a folder.")
            target = policy.check(dest, mutating=True)
        except SecurityError as exc:
            problems.append(str(exc))
        else:
            case_rename = (op.action == "rename_file" and op.source is not None
                           and same_path(target, op.source))
            if os.path.lexists(target) and not case_rename:
                problems.append(f"'{target}' already exists.")
            ext = target.suffix.lower()
            if op.action == "rename_file" and ext in cfg.blocked_extensions:
                problems.append("I won't rename a file into a program or script type.")
            if op.action == "create_text_file" and ext not in cfg.editable_extensions:
                problems.append("Text files must have an editable extension.")
    return problems


def _dispatch(op: Operation, tools: Tools, backup_dir) -> ToolResult:
    a = op.action
    if a == "create_folder":
        return tools.create_folder(op.destination)
    if a == "create_text_file":
        return tools.create_text_file(op.destination)
    if a in ("move_file", "rename_file"):
        return tools.move_path(op.source, op.destination, action=a)
    if a == "move_to_recycle_bin":
        return tools.move_to_recycle_bin(op.source)
    if a == "edit_text_file":
        detail = dict(op.detail)
        operation = detail.pop("operation")
        return tools.edit_text(op.source, operation, backup_dir=backup_dir, **detail)
    if a == "open_file":
        return tools.open_path(op.source)
    if a == "copy_path_to_clipboard":
        return tools.copy_path_to_clipboard(op.source)
    raise ToolError(f"No tool exists for '{a}'.")


def _run_op(idx: int, op: Operation, policy: PathPolicy, tools: Tools, journal: Journal,
            backup_dir, warnings: list[str]) -> OperationOutcome:
    def outcome(status: str, message: str, **kw) -> OperationOutcome:
        return OperationOutcome(index=idx, task_id=op.task_id, action=op.action,
                                description=op.describe(), status=status, message=message, **kw)

    if (op.action == "move_file" and op.source and op.destination
            and same_path(op.source, op.destination)):
        return outcome("unchanged", "Already in that folder, so nothing to do.")

    problems = guard(policy, op)                      # 1. security, right now
    if problems:
        return outcome("failed", "Not run: " + "; ".join(problems))
    if op.action == "edit_text_file" and backup_dir is None:
        return outcome("failed", "Not run: edits need a backup folder, so they can be undone.")

    try:                                              # 2. intent is recorded BEFORE the change
        journal.before(idx, op)
    except Exception as exc:
        return outcome("failed", f"Not run: I couldn't write the safety journal ({exc}).")

    try:                                              # 3. the change; the tool verifies itself
        res = _dispatch(op, tools, backup_dir)
    except ToolError as exc:
        oc = outcome("failed", str(exc), partial=exc.partial)
    except Exception as exc:
        oc = outcome("failed", f"Unexpected error ({type(exc).__name__}): {exc}",
                     partial={"note": "The state of this item is unknown. Please check it."})
    else:
        oc = outcome("done", res.message, output=res.output, undo=res.undo, verified=res.verified)

    try:                                              # 4. record what happened
        journal.after(idx, op, oc)
    except Exception as exc:
        warnings.append(f"The journal couldn't record step {idx} ({exc}). "
                        "Its undo information is only in this report.")
    return oc


def execute(plan: ExecutionPlan, policy: PathPolicy, approval: Approval | None = None, *,
            tools: Tools | None = None, journal: Journal | None = None, backup_dir=None,
            cancel: Callable[[], bool] | None = None,
            on_progress: Callable[[str, str], None] | None = None,
            now: float | None = None) -> ExecutionReport:
    """Run an approved plan. Raises PlanningError if the plan is malformed, or ApprovalError
    if it has problems or the approval doesn't match what would run now. In both cases
    nothing has been changed."""
    tools, journal, cancel = tools or Tools(), journal or NullJournal(), cancel or (lambda: False)
    order = validate_plan(plan)
    prepared = prepare(plan, policy)                  # fresh preview, right now
    check_approval(prepared, approval, now=now)

    by_id = {t.task_id: t for t in plan.tasks}
    reads = {r.task_id: r for r in prepared.reads}
    ops_by_task: dict[str, list[tuple[int, Operation]]] = {}
    for idx, op in enumerate(prepared.operations):
        ops_by_task.setdefault(op.task_id, []).append((idx, op))

    status_of: dict[str, str] = {}
    results: list[TaskResult] = []
    outcomes: list[OperationOutcome] = []
    warnings: list[str] = []
    cancelled = False

    def notify(tid: str, status: str) -> None:
        if on_progress:
            try:
                on_progress(tid, status)
            except Exception:
                pass                                  # a UI callback must never break execution

    def record(tid, status, task_outcomes, error=None, extra=None):
        status_of[tid] = status
        if status == "success":
            checked = [o for o in task_outcomes if o.status in ("done", "unchanged")]
            ver = (VerificationStatus.VERIFIED if all(o.verified for o in checked)
                   else VerificationStatus.NOT_CHECKED)
        elif status == "failed":
            ver = VerificationStatus.FAILED
        else:
            ver = VerificationStatus.NOT_CHECKED
        output = {"operations": [o.to_dict() for o in task_outcomes], **(extra or {})}
        results.append(TaskResult(task_id=tid, status=status, output=output,
                                  error=error, verification_status=ver))
        notify(tid, status)

    journal.start(plan.plan_id, prepared.digest, prepared.operations)
    try:
        for tid in order:
            task = by_id[tid]
            if not cancelled and cancel():
                cancelled = True
            if cancelled:
                record(tid, "cancelled", [], error="Cancelled before it started.")
                continue
            bad = next((d for d in task.dependencies if status_of.get(d) != "success"), None)
            if bad:
                record(tid, "cancelled", [], error=f"Skipped because {bad} didn't finish.")
                continue

            notify(tid, "running")
            if task.action in READ_ONLY:              # these already ran during prepare()
                r = reads.get(tid)
                record(tid, "success", [], extra={
                    "count": r.count if r else 0, "scope": r.scope if r else "",
                    "truncated": r.truncated if r else False, "sample": r.sample if r else []})
                continue

            ops = ops_by_task.get(tid, [])
            if not ops:
                record(tid, "failed", [], error="This step had nothing to run.")
                continue

            task_outcomes: list[OperationOutcome] = []
            failure: OperationOutcome | None = None
            halted = False
            for idx, op in ops:
                if not halted and failure is None and cancel():
                    cancelled = halted = True
                if halted or failure is not None:
                    why = "Cancelled." if halted else "Skipped because an earlier step failed."
                    oc = OperationOutcome(idx, op.task_id, op.action, op.describe(), "skipped", why)
                else:
                    oc = _run_op(idx, op, policy, tools, journal, backup_dir, warnings)
                    if oc.status == "failed":
                        failure = oc
                task_outcomes.append(oc)
                outcomes.append(oc)

            if failure is not None:
                record(tid, "failed", task_outcomes,
                       error=f"{failure.description}: {failure.message}")
            elif halted:
                record(tid, "cancelled", task_outcomes, error="Cancelled before this step finished.")
            else:
                record(tid, "success", task_outcomes)
    except BaseException:
        try:
            journal.finish("aborted")
        except Exception:
            pass
        raise

    if all(status_of.get(t) == "success" for t in order):
        status = PlanStatus.COMPLETED
    elif any(s == "failed" for s in status_of.values()):
        status = PlanStatus.FAILED
    elif cancelled:
        status = PlanStatus.CANCELLED
    else:
        status = PlanStatus.FAILED
    try:
        journal.finish(status.value)
    except Exception as exc:
        warnings.append(f"The journal couldn't record the final status ({exc}).")
    return ExecutionReport(plan.plan_id, prepared.digest, status, results, outcomes, warnings)