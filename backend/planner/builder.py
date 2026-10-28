from __future__ import annotations
import re
import uuid
from datetime import date
from pathlib import PureWindowsPath

from backend.nlp.result import Entities, NLPResult, NLPStatus
from backend.schemas.plan import ExecutionPlan
from backend.schemas.task import Task

from .actions import ACTIONS, APPROVAL_RISKS, SUPPORTED_ACTIONS
from .dates import build_date_filter
from .errors import PlanningError
from .validator import validate_plan
from .references import (REFERENCE_ACTIONS, SINGLE_TARGET_ACTIONS, ref_dependencies,
                         resolve_reference, risk_for_reference)


def _explicit_targets(e: Entities, include_texts: bool) -> list[dict]:
    """Files/folders the user named: paths, then filenames, then names (no duplicates)."""
    groups = [("path", e.paths), ("filename", e.filenames), ("name", e.names)]
    if include_texts:   # a quoted non-file string like "My Old Folder" is a name
        groups.append(("name", e.texts))
    out, seen = [], set()
    for kind, values in groups:
        for value in values:
            if value.casefold() not in seen:
                seen.add(value.casefold())
                out.append({kind: value})
    return out


def _plain_name(value: str, what: str) -> str:
    if "/" in value or "\\" in value:
        raise PlanningError(f"{what} must be a plain name, not a path: {value}")
    return value


_DRIVE = re.compile(r"^[A-Za-z]:\\")


def _scope(e: Entities) -> dict | None:
    """'in Downloads' or 'in D:\\Work' becomes a folder reference; the security layer resolves it."""
    if len(e.locations) > 1:
        raise PlanningError("I can only use one folder at a time.")
    if not e.locations:
        return None
    value = e.locations[0]
    is_path = bool(_DRIVE.match(value)) or "/" in value or "\\" in value
    return {"path": value} if is_path else {"name": value}


def _creation_params(e: Entities, text_file: bool, scope: dict | None = None) -> dict:
    if e.paths:
        if scope:
            raise PlanningError("Give a full path, or a name plus a folder, not both.")
        path = e.paths[0]
        if text_file and not PureWindowsPath(path).suffix:
            path += ".txt"
        return {"path": path}
    candidates = [*e.filenames, *e.names, *e.texts]
    if not candidates:
        raise PlanningError("I need a name for what to create.")
    name = _plain_name(candidates[0], "The name")
    if text_file and "." not in name:
        name += ".txt"
    params: dict = {"name": name}
    if scope:
        params["parent"] = scope
    return params

def _params(action: str, e: Entities, ref: dict | None = None,
            today: date | None = None) -> dict:
    if (e.references or e.sort_by) and ref is None:
        raise PlanningError("Only actions on existing files can refer to earlier results "
                            "('the largest', 'the rest', 'it').")
    date_filter = None
    if e.dates:
        if action not in ("search_files", "list_files"):
            raise PlanningError("Date filters only work with searching and listing. Search "
                                "first, e.g. 'find PDFs older than 30 days, then delete them'.")
        date_filter = build_date_filter(e.dates, e.date_field, today or date.today())
    scope = _scope(e)

    if action == "search_files":
        names = [*e.names, *e.texts]
        if not (e.filenames or names or e.file_types or date_filter):
            raise PlanningError("I need something to search for.")
        return {"filenames": e.filenames, "names": names, "file_types": e.file_types,
                "date_filter": date_filter, "scope": scope}
    if action == "list_files":
        targets = _explicit_targets(e, include_texts=True)
        if scope and targets:
            raise PlanningError("Name one folder to list.")
        if len(targets) > 1:
            raise PlanningError("I can list one folder at a time.")
        if targets and "filename" in targets[0]:
            raise PlanningError("That's a file, not a folder.")
        # scope None = the app's default folder (read-only, so acceptable)
        return {"scope": scope or (targets[0] if targets else None),
                "file_types": e.file_types, "date_filter": date_filter}
        targets = _explicit_targets(e, include_texts=True)
        if len(targets) > 1:
            raise PlanningError("I can list one folder at a time.")
        # location None = the executor's default folder (acceptable: listing is read-only)
        return {"location": targets[0] if targets else None,
                "file_types": e.file_types, "date_filter": date_filter}

    if action == "create_folder":
        return _creation_params(e, text_file=False, scope=scope)
    if action == "create_text_file":
        return _creation_params(e, text_file=True, scope=scope)

    # ---- actions on EXISTING files: need specific, named targets ----
    if e.locations:
        raise PlanningError("I can't yet tell which folder you mean for this action. "
                            "Please give the full path of the file instead.")
    if ref is not None:
        targets = [ref]          # chosen at run time from an earlier task's results
    else:
        if e.file_types:
            raise PlanningError("That refers to a kind of file (like 'all PDFs'). I need "
                                "specific file names; picking files by type isn't supported yet.")
        targets = _explicit_targets(e, include_texts=(action != "edit_text_file"))
        if not targets:
            raise PlanningError("I need to know which file or folder.")
    if action in SINGLE_TARGET_ACTIONS and len(targets) != 1:
        raise PlanningError(f"This works on one file at a time, but I found {len(targets)}.")

    if action in ("open_file", "copy_path_to_clipboard"):
        return {"target": targets[0]}
    if action == "move_to_recycle_bin":
        return {"targets": targets}
    if action == "move_file":
        if not e.destination:
            raise PlanningError("I need the destination folder.")
        return {"targets": targets, "destination": e.destination}
    if action == "rename_file":
        if not e.new_name:
            raise PlanningError("I need the new name.")
        return {"target": targets[0], "new_name": _plain_name(e.new_name, "The new name")}
    if action == "edit_text_file":
        if e.edit_op == "append" and len(e.texts) == 1:
            return {"target": targets[0], "operation": "append", "text": e.texts[0]}
        if e.edit_op == "replace" and len(e.texts) == 2:
            return {"target": targets[0], "operation": "replace",
                    "old_text": e.texts[0], "new_text": e.texts[1]}
        raise PlanningError("I need one quoted text to add, or an old and a new quoted "
                            "text to replace.")
    raise PlanningError(f"Unsupported action: {action}")


def build_plan(nlp: NLPResult, request_id: str | None = None,
               today: date | None = None) -> ExecutionPlan:
    # Defense in depth: never trust that the caller checked.
    if nlp.status != NLPStatus.OK:
        raise PlanningError("Only fully understood requests can be planned.")

    today = today or date.today()      # one fixed "today" for the whole plan
    tasks: list[Task] = []
    for i, clause in enumerate(nlp.clauses, start=1):
        if clause.status != NLPStatus.OK or clause.intent not in ACTIONS:
            raise PlanningError(f'"{clause.text}" can\'t be planned.')
        action, risk = ACTIONS[clause.intent]
        assert action in SUPPORTED_ACTIONS
        
        
        e = clause.entities
        try:
            ref = None
            if action in REFERENCE_ACTIONS:
                explicit = _explicit_targets(e, include_texts=(action != "edit_text_file"))
                if explicit and (e.references or e.sort_by):
                    raise PlanningError("Name the file, or refer to an earlier result, but not both.")
                if not explicit and (e.references or e.sort_by or e.file_types):
                    ref = resolve_reference(action, e, tasks)
            params = _params(action, e, ref,today)
        except PlanningError as exc:
            raise PlanningError(f'"{clause.text}": {exc}') from exc

        deps = [f"t{i - 1}"] if i > 1 else []      # sequential: a failure stops the rest
        approval = risk in APPROVAL_RISKS
        if ref is not None:
            deps = list(dict.fromkeys([*deps, *ref_dependencies(ref)]))
            risk = risk_for_reference(risk, ref["select"])
            approval = True      # the user hasn't seen which file(s) this will hit
        tasks.append(Task(
            task_id=f"t{i}",
            action=action,
            parameters=params,
            dependencies=deps,
            risk_level=risk,
            approval_required=approval,
        ))
    plan = ExecutionPlan(
        plan_id=uuid.uuid4().hex,
        request_id=request_id or uuid.uuid4().hex,
        tasks=tasks,
    )
    validate_plan(plan)      # last gate: nothing unvalidated leaves the planner
    return plan