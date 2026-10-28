from __future__ import annotations

from typing import Protocol

from .prepare import Operation
from .report import OperationOutcome


class Journal(Protocol):
    def start(self, plan_id: str, digest: str, operations: list[Operation]) -> None: ...
    def before(self, index: int, op: Operation) -> None: ...
    def after(self, index: int, op: Operation, outcome: OperationOutcome) -> None: ...
    def finish(self, status: str) -> None: ...


class NullJournal:
    """Records nothing. Placeholder until the real journal exists."""
    def start(self, plan_id, digest, operations): pass
    def before(self, index, op): pass
    def after(self, index, op, outcome): pass
    def finish(self, status): pass


class MemoryJournal:
    """Keeps events in a list. Used by tests."""
    def __init__(self):
        self.events: list[tuple] = []

    def start(self, plan_id, digest, operations):
        self.events.append(("start", plan_id, digest, len(operations)))

    def before(self, index, op):
        self.events.append(("before", index))

    def after(self, index, op, outcome):
        self.events.append(("after", index, outcome.status))

    def finish(self, status):
        self.events.append(("finish", status))