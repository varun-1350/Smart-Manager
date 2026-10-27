
from enum import Enum

from pydantic import BaseModel, Field

from backend.schemas.task import Task


class PlanStatus(str, Enum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionPlan(BaseModel):
    plan_id: str
    request_id: str
    tasks: list[Task] = Field(min_length=1)
    status: PlanStatus = PlanStatus.DRAFT
