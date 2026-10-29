from __future__ import annotations

import hmac
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from backend.execution.approval import ApprovalError, grant
from backend.execution.engine import Tools, execute
from backend.execution.file_journal import FileJournal, acknowledge, find_interrupted, record_undo
from backend.execution.prepare import Prepared, prepare
from backend.execution.recovery import RecoveryReport, recovery_report
from backend.execution.report import ExecutionReport
from backend.execution.undo import UndoOutcome, describe_step, run_undo
from backend.nlp.pipeline import analyze
from backend.nlp.result import NLPStatus
from backend.planner.builder import build_plan
from backend.planner.errors import PlanningError
from backend.schemas.plan import ExecutionPlan
from backend.security.paths import PathPolicy

MAX_INPUT_CHARS = 1000
MAX_PENDING = 10


@dataclass
class Turn:
    """What the UI shows after one step. kind: clarify | unsupported | error | blocked |
    needs_approval | executed."""
    turn_id: str
    kind: str
    message: str
    digest: str = ""                       # for needs_approval: the UI sends it back to approve
    report: ExecutionReport | None = None


@dataclass
class _Pending:
    plan: ExecutionPlan
    prepared: Prepared
    created: float


class Assistant:
    def __init__(self, classifier, policy: PathPolicy, journal_dir, backup_dir, *,
                 tools: Tools | None = None, pending_ttl: float = 300.0,
                 clock: Callable[[], float] = time.time,
                 today: Callable[[], date] = date.today):
        self.classifier, self.policy = classifier, policy
        self.journal_dir, self.backup_dir = journal_dir, backup_dir
        self.tools, self.pending_ttl = tools, pending_ttl
        self._clock, self._today = clock, today
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()          # one execution at a time
        self._cancel = threading.Event()
        self._last: tuple[ExecutionReport, object] | None = None

    # ----------------------------------------------------------- helpers
    @staticmethod
    def _turn(kind: str, message: str, **kw) -> Turn:
        return Turn(uuid.uuid4().hex, kind, message, **kw)

    def _purge(self) -> None:
        now = self._clock()
        for tid in [t for t, p in self._pending.items() if now - p.created > self.pending_ttl]:
            del self._pending[tid]
        while len(self._pending) > MAX_PENDING:
            del self._pending[min(self._pending, key=lambda t: self._pending[t].created)]

    # -------------------------------------------------------------- steps
    def handle(self, text) -> Turn:
        """Text in. Nothing is changed here unless the plan needs no approval."""
        self._purge()
        if not isinstance(text, str) or not text.strip():
            return self._turn("clarify", "Please type a request.")
        if len(text) > MAX_INPUT_CHARS or "\x00" in text:
            return self._turn("error", "That request is too long or has characters I can't read.")

        nlp = analyze(text, self.classifier)
        if nlp.status != NLPStatus.OK:
            reasons = [c.reason for c in nlp.clauses if c.status != NLPStatus.OK and c.reason]
            message = " ".join(dict.fromkeys(reasons)) or "I didn't understand that."
            kind = "unsupported" if nlp.status == NLPStatus.UNSUPPORTED else "clarify"
            return self._turn(kind, message)

        try:
            plan = build_plan(nlp, today=self._today())
            prepared = prepare(plan, self.policy)
        except PlanningError as exc:
            return self._turn("error", str(exc))
        if not prepared.ok:
            return self._turn("blocked", "I can't do that:\n"
                              + "\n".join(f"- {p}" for p in prepared.problems))
        if not prepared.needs_approval:
            return self._run(plan, None)

        turn = self._turn("needs_approval", prepared.summary(), digest=prepared.digest)
        self._pending[turn.turn_id] = _Pending(plan, prepared, self._clock())
        self._purge()
        return turn

    def approve(self, turn_id: str, digest: str) -> Turn:
        """The user approved exactly what they were shown (identified by its digest)."""
        self._purge()
        pending = self._pending.get(turn_id)
        if pending is None:
            return self._turn("error", "That request is no longer waiting for approval. "
                                       "It may have expired.")
        if not hmac.compare_digest(str(digest or "").encode(), pending.prepared.digest.encode()):
            return self._turn("error", "That approval doesn't match what was shown. "
                                       "Nothing was done.")
        del self._pending[turn_id]               # one approval, one run
        return self._run(pending.plan, grant(pending.prepared))

    def reject(self, turn_id: str) -> None:
        self._pending.pop(turn_id, None)

    def request_cancel(self) -> None:
        self._cancel.set()

    def _run(self, plan: ExecutionPlan, approval) -> Turn:
        if not self._lock.acquire(blocking=False):
            return self._turn("error", "Another request is still running. Please wait for it.")
        try:
            self._cancel.clear()
            journal = FileJournal(self.journal_dir)
            try:
                report = execute(plan, self.policy, approval, tools=self.tools, journal=journal,
                                 backup_dir=self.backup_dir, cancel=self._cancel.is_set)
            except (ApprovalError, PlanningError) as exc:
                return self._turn("error", f"{exc} Nothing was changed.")
            except OSError as exc:
                return self._turn("error", f"I couldn't start the safety journal ({exc}). "
                                           "Nothing was changed.")
            self._last = (report, journal.path) if report.undo_steps() else None
            return self._turn("executed", report.summary(), report=report)
        finally:
            self._lock.release()

    # --------------------------------------------------------------- undo
    def undo_preview(self) -> list[str]:
        if self._last is None:
            return []
        return [describe_step(s) for s in self._last[0].undo_steps()]

    def undo_last(self, *, confirmed: bool = False) -> list[UndoOutcome]:
        """Reverse the last execution. The UI must show undo_preview() and ask first."""
        if not confirmed:
            raise PermissionError("Undo needs explicit confirmation.")
        if self._last is None:
            return []
        report, journal_path = self._last
        outcomes = self.run_undo_steps(report.undo_steps(), confirmed=True)
        self._last = None
        if journal_path:
            try:
                record_undo(journal_path, outcomes)
            except OSError:
                pass
        return outcomes

    def run_undo_steps(self, steps: list[dict], *, confirmed: bool = False) -> list[UndoOutcome]:
        if not confirmed:
            raise PermissionError("Undo needs explicit confirmation.")
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Another request is still running.")
        try:
            return run_undo(steps, self.policy)
        finally:
            self._lock.release()

    # ----------------------------------------------------------- recovery
    def interrupted(self) -> tuple[list[RecoveryReport], list[str]]:
        """Call once at startup, before any request: earlier runs that never finished."""
        runs, errors = find_interrupted(self.journal_dir)
        return [recovery_report(r, self.backup_dir) for r in runs], errors

    def _find_interrupted(self, run_id):
        runs, _ = find_interrupted(self.journal_dir)
        name = Path(str(run_id)).name       # match only against the server's own list
        return next((r for r in runs if r.path.name == name), None)

    def dismiss_interrupted(self, run_id) -> None:
        run = self._find_interrupted(run_id)
        if run is None:
            raise LookupError("That interrupted run wasn't found.")
        acknowledge(run.path, "reviewed by the user")

    def undo_interrupted(self, run_id, *, confirmed: bool = False) -> list[UndoOutcome]:
        """Undo what an interrupted run is known to have done. The steps come from the
        journal and the disk, never from the caller."""
        if not confirmed:
            raise PermissionError("Undo needs explicit confirmation.")
        run = self._find_interrupted(run_id)
        if run is None:
            raise LookupError("That interrupted run wasn't found.")
        steps = recovery_report(run, self.backup_dir).undo_steps
        outcomes = self.run_undo_steps(steps, confirmed=True)
        try:
            record_undo(run.path, outcomes)
        except OSError:
            pass
        return outcomes