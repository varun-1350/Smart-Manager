from __future__ import annotations

from typing import Any

from backend.nlp.result import Entities
from backend.schemas.task import RiskLevel, Task

from .errors import PlanningError

# tasks whose output other tasks can refer to
RESULT_PRODUCERS = frozenset({"search_files", "list_files"})
ITEM_PRODUCERS = RESULT_PRODUCERS | {"create_folder", "create_text_file"}

# actions on EXISTING files: the only ones allowed to use references
REFERENCE_ACTIONS = frozenset({"open_file", "rename_file", "edit_text_file",
                               "copy_path_to_clipboard", "move_file", "move_to_recycle_bin"})
SINGLE_TARGET_ACTIONS = frozenset({"open_file", "rename_file", "edit_text_file",
                                   "copy_path_to_clipboard"})

REST_WORDS = frozenset({"the rest", "the remaining", "the others"})
PLURAL_WORDS = frozenset({"them", "those", "these"})
SINGLE_WORDS = frozenset({"it", "that file"})
MULTI_SELECTS = frozenset({"all", "remaining"})

_RISK_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.DESTRUCTIVE]


def _contains_ref(value: Any, task_id: str) -> bool:
    """Does this parameter structure point at `task_id`?"""
    if isinstance(value, dict):
        return value.get("from_task") == task_id or any(
            _contains_ref(v, task_id) for v in value.values())
    if isinstance(value, list):
        return any(_contains_ref(v, task_id) for v in value)
    return False


def _last_producer(tasks: list[Task], kinds: frozenset[str]) -> tuple[int, Task] | None:
    for idx in range(len(tasks) - 1, -1, -1):
        if tasks[idx].action in kinds:
            return idx, tasks[idx]
    return None


def _check_types(wanted: list[str], producer: Task) -> None:
    if not wanted:
        return
    have = set(producer.parameters.get("file_types", []))
    missing = set(wanted) - have
    if missing:
        raise PlanningError(f"The earlier step didn't look for {', '.join(sorted(missing))} files.")


def resolve_reference(action: str, e: Entities, tasks: list[Task]) -> dict:
    """Turn 'the largest', 'the rest', 'them', 'it' into a pointer at an earlier task.
    Anything unclear is refused, never guessed."""
    refs = set(e.references)
    rest, plural, single = refs & REST_WORDS, refs & PLURAL_WORDS, refs & SINGLE_WORDS
    sort = e.sort_by

    if (sort and (rest or single)) or (rest and single) or (plural and single):
        raise PlanningError("I can't tell which files you mean. Please name them.")

    # ---- "it" / "that file": ONE specific item ----
    if single:
        found = _last_producer(tasks, ITEM_PRODUCERS)
        if not found:
            raise PlanningError("'it' has nothing earlier to refer to. Please name the file.")
        idx, producer = found
        # every step in between must have been about that same item
        if not all(_contains_ref(t.parameters, producer.task_id) for t in tasks[idx + 1:]):
            raise PlanningError("It isn't clear what 'it' refers to. Please name the file.")
        if action == "edit_text_file" and producer.action == "create_folder":
            raise PlanningError("A folder can't be edited as a text file.")
        select = "created" if producer.action.startswith("create_") else "only"
        return {"from_task": producer.task_id, "select": select}

    # ---- sets of results: "the largest", "the rest", "them", "all PDFs" ----
    found = _last_producer(tasks, RESULT_PRODUCERS)
    if not found:
        raise PlanningError("There is no earlier search or list for that to refer to. "
                            "Please name the file, or search first.")
    idx, producer = found
    _check_types(e.file_types, producer)

    used: list[str] = []
    if sort:
        select = sort
    elif rest:
        used = [t.task_id for t in tasks[idx + 1:] if _contains_ref(t.parameters, producer.task_id)]
        if not used:
            raise PlanningError("'The rest' needs an earlier step that picked some files first.")
        select = "remaining"
    else:
        select = "all"

    if action in SINGLE_TARGET_ACTIONS and select in MULTI_SELECTS:
        raise PlanningError("This works on one file at a time, but that refers to several.")

    ref: dict[str, Any] = {"from_task": producer.task_id, "select": select}
    if used:
        ref["except_tasks"] = used
    return ref


def ref_dependencies(ref: dict) -> list[str]:
    return [ref["from_task"], *ref.get("except_tasks", [])]


def risk_for_reference(base: RiskLevel, select: str) -> RiskLevel:
    """The user hasn't seen which file(s) this will hit, so raise the floor."""
    floor = RiskLevel.HIGH if select in MULTI_SELECTS else RiskLevel.MEDIUM
    return max(base, floor, key=_RISK_ORDER.index)