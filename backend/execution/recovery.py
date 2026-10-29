from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from backend.security.pathutil import same_path
from backend.tools.filesystem.common import sha256_file

from .file_journal import JournalRun, Step
from .prepare import Operation

NO_FILE_EFFECT = frozenset({"open_file", "copy_path_to_clipboard"})


@dataclass
class StepState:
    index: int
    description: str
    state: str            # done | not_done | unclear | harmless
    note: str
    undo: dict | None = None


@dataclass
class RecoveryReport:
    run_path: str
    plan_id: str
    unknown: list[StepState]
    completed: list[dict] = field(default_factory=list)    # steps that finished before the crash
    undo_steps: list[dict] = field(default_factory=list)   # newest first, safe to offer
    damaged: bool = False


def _describe(op: dict, index: int) -> str:
    try:
        return Operation(op["task_id"], op["action"], op.get("source"), op.get("destination"),
                         op.get("detail") or {}, op.get("risk", ""),
                         tuple(op.get("warnings", ()))).describe()
    except (KeyError, TypeError, AttributeError):
        return f"step {index}"


def _inspect(step: Step, backup_dir) -> tuple[str, str, dict | None]:
    """What does the disk say about a step that started but never reported back?"""
    op = step.op
    action, src, dst = op.get("action"), op.get("source"), op.get("destination")

    if action in NO_FILE_EFFECT:
        return "harmless", "This step doesn't change any files.", None

    if action in ("move_file", "rename_file"):
        if not src or not dst:
            return "unclear", "The journal doesn't say where this step was going.", None
        undo = {"op": "move_back", "from": dst, "to": src}
        if same_path(src, dst):                                    # only the capitals changed
            try:
                renamed = Path(dst).name in os.listdir(Path(dst).parent)
            except OSError:
                return "unclear", "I couldn't look at the folder.", None
            return (("done", "The name was changed.", undo) if renamed
                    else ("not_done", "The name was not changed.", None))
        there_src, there_dst = os.path.lexists(src), os.path.lexists(dst)
        if there_src and not there_dst:
            return "not_done", "Nothing was moved. The file is still where it was.", None
        if there_dst and not there_src:
            return "done", "It was moved before the interruption.", undo
        if there_src and there_dst:
            return "unclear", "The file exists in BOTH places. Please check them.", None
        return "unclear", "The file is in neither place. It may have been moved or removed.", None

    if action in ("create_folder", "create_text_file"):
        if dst and os.path.lexists(dst):
            kind = "remove_empty_folder" if action == "create_folder" else "remove_empty_file"
            return "done", "It was created before the interruption.", {"op": kind, "path": dst}
        return "not_done", "It was not created.", None

    if action == "move_to_recycle_bin":
        if src and os.path.lexists(src):
            return "not_done", "The item is still where it was.", None
        return ("done", "The item is gone from its folder, probably in the Recycle Bin.",
                {"op": "restore_from_recycle_bin", "path": src, "manual": True})

    if action == "edit_text_file":
        before = step.before_sha256
        if not src or not before or not os.path.isfile(src):
            return "unclear", "I can't tell whether the edit happened.", None
        try:
            current = sha256_file(src)
        except OSError:
            return "unclear", "I couldn't read the file.", None
        if current == before:
            return "not_done", "The file is unchanged.", None
        backup = Path(backup_dir) / f"{before[:16]}-{Path(src).name}.bak" if backup_dir else None
        if backup and backup.is_file() and sha256_file(backup) == before:
            return ("unclear", "The file differs from before the edit, so the edit may have "
                    "been partly or fully applied. A backup of the original exists.",
                    {"op": "restore_backup", "path": src, "backup": str(backup),
                     "expected_sha256": current})
        return "unclear", "The file differs from before the edit and I found no backup.", None

    return "unclear", "I don't recognise this step.", None


def recovery_report(run: JournalRun, backup_dir=None) -> RecoveryReport:
    """Compare what the journal says with what is really on disk."""
    unknown = [StepState(s.index, _describe(s.op, s.index), *_inspect(s, backup_dir))
               for s in run.unknown_steps()]
    completed, undoable = [], []
    for idx, step in sorted(run.steps.items()):
        out = step.outcome
        if out and out.get("status") == "done" and out.get("undo"):
            completed.append({"index": idx, "description": _describe(step.op, idx),
                              "undo": out["undo"]})
            undoable.append((idx, out["undo"]))
    undoable += [(s.index, s.undo) for s in unknown if s.state == "done" and s.undo]
    undoable.sort(key=lambda pair: pair[0], reverse=True)
    return RecoveryReport(str(run.path), run.plan_id, unknown, completed,
                          [u for _, u in undoable], run.damaged)