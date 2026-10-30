from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from backend.execution.recovery import RecoveryReport
from backend.execution.report import ExecutionReport
from backend.execution.undo import UndoOutcome, describe_step
from backend.services.assistant import Turn
from backend.execution.prepare import Prepared


def _dump(model) -> dict:
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else json.loads(model.json())


def report_to_dict(r: ExecutionReport) -> dict:
    return {
        "plan_id": r.plan_id,
        "status": r.status.value,
        "succeeded": r.succeeded,
        "partial": r.partial,
        "summary": r.summary(),
        "results": [_dump(x) for x in r.results],
        "outcomes": [o.to_dict() for o in r.outcomes],
        "warnings": list(r.warnings),
        "undo_available": bool(r.undo_steps()),
    }

def preview_to_dict(p: Prepared) -> dict:
    return {
        "reads": [{"task_id": r.task_id, "action": r.action, "scope": r.scope,
                   "count": r.count, "truncated": r.truncated, "sample": r.sample}
                  for r in p.reads],
        "operations": [{"task_id": o.task_id, "action": o.action, "description": o.describe(),
                        "source": o.source, "destination": o.destination, "risk": o.risk,
                        "warnings": list(o.warnings)} for o in p.operations],
        "needs_approval": p.needs_approval,
    }


def turn_to_dict(t: Turn) -> dict:
    return {"turn_id": t.turn_id, "kind": t.kind, "message": t.message, "digest": t.digest,
            "report": report_to_dict(t.report) if t.report else None,
            "preview": (preview_to_dict(t.prepared)
                        if t.prepared is not None and t.kind == "needs_approval" else None)}

def undo_outcomes_to_dict(outcomes: list[UndoOutcome]) -> list[dict]:
    return [{"description": describe_step(o.step), "status": o.status, "message": o.message}
            for o in outcomes]


def recovery_to_dict(rep: RecoveryReport) -> dict:
    return {
        "run_id": Path(rep.run_path).name,           # a name, never a full path
        "plan_id": rep.plan_id,
        "damaged": rep.damaged,
        "unknown": [asdict(s) for s in rep.unknown],
        "completed": rep.completed,
        "undo_preview": [describe_step(s) for s in rep.undo_steps],
    }