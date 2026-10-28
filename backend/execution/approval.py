from __future__ import annotations

import hmac
import time
from dataclasses import dataclass

from .prepare import Prepared

DEFAULT_TTL_SECONDS = 600


class ApprovalError(Exception):
    """Execution must not go ahead. The message is safe to show to the user."""


@dataclass(frozen=True)
class Approval:
    plan_id: str
    digest: str
    granted_at: float


def grant(prepared: Prepared, now: float | None = None) -> Approval:
    """Record that the user approved exactly what `prepared` showed."""
    if not prepared.ok:
        raise ApprovalError("This plan has problems and can't be approved: "
                            + "; ".join(prepared.problems[:3]))
    return Approval(prepared.plan_id, prepared.digest, time.time() if now is None else now)


def check(prepared: Prepared, approval: Approval | None, now: float | None = None,
          ttl: float = DEFAULT_TTL_SECONDS) -> None:
    """Call with a FRESH prepare() result right before executing. Raises unless the plan is
    clean and, where required, the approval matches exactly what would run now."""
    if not prepared.ok:
        raise ApprovalError("This plan has problems and can't run: "
                            + "; ".join(prepared.problems[:3]))
    if approval is None:
        if prepared.needs_approval:
            raise ApprovalError("This plan needs your approval before it can run.")
        return
    if approval.plan_id != prepared.plan_id:
        raise ApprovalError("This approval belongs to a different plan.")
    if not hmac.compare_digest(approval.digest, prepared.digest):
        raise ApprovalError("Your files have changed since you approved this. "
                            "Please review the plan again.")
    age = (time.time() if now is None else now) - approval.granted_at
    if age < 0 or age > ttl:
        raise ApprovalError("Your approval has expired. Please review the plan again.")