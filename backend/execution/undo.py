from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from backend.security.errors import SecurityError
from backend.security.pathutil import same_path
from backend.security.paths import PathPolicy
from backend.security.preflight import action_rules
from backend.tools.filesystem import files
from backend.tools.filesystem.common import ToolError, sha256_file

from .engine import guard
from .prepare import Operation


@dataclass
class UndoOutcome:
    step: dict
    status: str          # undone | failed | manual
    message: str


def describe_step(step: dict) -> str:
    op = step.get("op")
    if op == "move_back":
        return f"Move {step.get('from')} back to {step.get('to')}"
    if op == "remove_empty_folder":
        return f"Remove the empty folder {step.get('path')}"
    if op == "remove_empty_file":
        return f"Remove the empty file {step.get('path')}"
    if op == "restore_backup":
        return f"Restore {step.get('path')} from its backup"
    if op == "restore_from_recycle_bin":
        return f"Restore {step.get('path')} from the Recycle Bin (by hand)"
    return f"Unknown undo step: {op}"


def _move_back(step: dict, policy: PathPolicy) -> str:
    src, dst = step["from"], step["to"]
    action = "rename_file" if same_path(src, dst) else "move_file"
    problems = guard(policy, Operation("undo", action, src, dst, {}, "high"))
    if problems:
        raise ToolError("; ".join(problems))
    files.move_path(src, dst, action="move_file")
    return f"Moved {Path(src).name} back to {Path(dst).parent}"


def _remove_empty_folder(step: dict, policy: PathPolicy) -> str:
    real = policy.check(step["path"], mutating=True, must_exist=True)
    if not real.is_dir():
        raise ToolError(f"'{real}' isn't a folder.")
    if os.listdir(real):
        raise ToolError(f"'{real.name}' isn't empty now. I only remove empty folders.")
    os.rmdir(real)
    if os.path.lexists(real):
        raise ToolError(f"'{real.name}' is still there after removing it.")
    return f"Removed the empty folder {real.name}"


def _remove_empty_file(step: dict, policy: PathPolicy) -> str:
    real = policy.check(step["path"], mutating=True, must_exist=True)
    if not real.is_file():
        raise ToolError(f"'{real}' isn't a file.")
    if real.stat().st_size != 0:
        raise ToolError(f"'{real.name}' has content now. I only remove files I created empty.")
    os.remove(real)
    if os.path.lexists(real):
        raise ToolError(f"'{real.name}' is still there after removing it.")
    return f"Removed the empty file {real.name}"


def _restore_backup(step: dict, policy: PathPolicy) -> str:
    real = policy.check(step["path"], mutating=True, must_exist=True)
    problems = action_rules(policy, "edit_text_file", real)
    if problems:
        raise ToolError("; ".join(problems))
    expected = step.get("expected_sha256")
    if not expected or sha256_file(real) != expected:
        raise ToolError(f"'{real.name}' has changed since the edit. I won't overwrite "
                        "later changes.")
    backup = Path(step["backup"])
    if not backup.is_file():
        raise ToolError("The backup file is missing.")
    want = sha256_file(backup)
    tmp = real.with_name(f".{real.name}.{uuid.uuid4().hex[:8]}.undo")
    try:
        shutil.copyfile(backup, tmp)
        if sha256_file(tmp) != want:
            raise ToolError("The restored copy didn't match the backup, so I stopped.")
        os.replace(tmp, real)
    finally:
        if os.path.lexists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    if sha256_file(real) != want:
        raise ToolError("The restored file doesn't match the backup.")
    return f"Restored {real.name} from its backup"


_HANDLERS = {"move_back": _move_back, "remove_empty_folder": _remove_empty_folder,
             "remove_empty_file": _remove_empty_file, "restore_backup": _restore_backup}


def run_undo(steps: list[dict], policy: PathPolicy) -> list[UndoOutcome]:
    """Reverse steps in the order given (newest first). Every step re-checks security and
    its own preconditions, so a step that no longer applies fails safely instead of
    guessing. A failure never stops the other steps."""
    outcomes: list[UndoOutcome] = []
    for step in steps:
        try:
            if step.get("op") == "restore_from_recycle_bin":
                name = Path(str(step.get("path", ""))).name
                outcomes.append(UndoOutcome(step, "manual",
                                f"Open the Recycle Bin and restore '{name}'. I can't do this "
                                "for you."))
                continue
            handler = _HANDLERS.get(step.get("op"))
            if handler is None:
                raise ToolError(f"I don't know how to undo '{step.get('op')}'.")
            outcomes.append(UndoOutcome(step, "undone", handler(step, policy)))
        except KeyError as exc:
            outcomes.append(UndoOutcome(step, "failed", f"The undo step is incomplete: {exc}"))
        except (SecurityError, ToolError, OSError) as exc:
            outcomes.append(UndoOutcome(step, "failed", str(exc) or type(exc).__name__))
    return outcomes