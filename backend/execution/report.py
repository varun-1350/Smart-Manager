from __future__ import annotations

from dataclasses import asdict, dataclass, field

from backend.schemas.plan import PlanStatus
from backend.schemas.result import TaskResult

from .prepare import STATE_CHANGING


@dataclass
class OperationOutcome:
    index: int
    task_id: str
    action: str
    description: str
    status: str                    # done | unchanged | failed | skipped
    message: str
    output: dict = field(default_factory=dict)
    undo: dict | None = None
    verified: bool = True
    partial: dict | None = None    # what may already have changed when it failed

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionReport:
    plan_id: str
    digest: str
    status: PlanStatus
    results: list[TaskResult]
    outcomes: list[OperationOutcome]
    warnings: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.status == PlanStatus.COMPLETED

    @property
    def changed_something(self) -> bool:
        return any(o.status == "done" and o.action in STATE_CHANGING for o in self.outcomes)

    @property
    def partial(self) -> bool:
        """Something was changed but the plan didn't finish."""
        return self.changed_something and not self.succeeded

    def undo_steps(self) -> list[dict]:
        """Undo information for everything that was done, newest first."""
        return [o.undo for o in reversed(self.outcomes) if o.status == "done" and o.undo]

    def summary(self) -> str:
        lines = [f"Result: {self.status.value}" + (" (partly done)" if self.partial else "")]
        for r in self.results:
            if "count" in r.output:
                o = r.output
                early = " (stopped early: too many matches)" if o.get("truncated") else ""
                lines.append(f"  {r.task_id}: found {o['count']} item(s) in {o['scope']}{early}")
                sample = o.get("sample", [])
                lines += [f"      {s}" for s in sample]
                if o["count"] > len(sample):
                    lines.append(f"      ... and {o['count'] - len(sample)} more")
        for o in self.outcomes:
            tail = "" if o.status == "done" else f": {o.message}"
            lines.append(f"  [{o.status}] {o.description}{tail}")
        for r in self.results:
            if r.status in ("failed", "cancelled") and r.error:
                lines.append(f"  {r.task_id} {r.status}: {r.error}")
        lines += [f"  warning: {w}" for w in self.warnings]
        return "\n".join(lines)