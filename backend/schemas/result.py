
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class VerificationStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    VERIFIED = "verified"
    FAILED = "failed"


class TaskResult(BaseModel):
    task_id: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    verification_status: VerificationStatus = (
        VerificationStatus.NOT_CHECKED
    )
