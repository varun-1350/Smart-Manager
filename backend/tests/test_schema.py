
import pytest
from pydantic import ValidationError

from backend.schemas import (
    ExecutionPlan,
    PlanStatus,
    Task,
    TaskResult,
    TaskStatus,
    UserRequest,
    VerificationStatus,
)


def test_valid_request():
    request = UserRequest(
        request_id="req-001",
        original_text="Find PNG files",
    )
    assert request.request_id == "req-001"


def test_empty_request_text_is_rejected():
    with pytest.raises(ValidationError):
        UserRequest(request_id="req-001", original_text="")


def test_task_defaults():
    task = Task(task_id="task-001", action="search_files")
    assert task.dependencies == []
    assert task.approval_required is False


def test_invalid_risk_level_is_rejected():
    with pytest.raises(ValidationError):
        Task(
            task_id="task-001",
            action="delete_file",
            risk_level="extreme",
        )


def test_plan_requires_at_least_one_task():
    with pytest.raises(ValidationError):
        ExecutionPlan(
            plan_id="plan-001",
            request_id="req-001",
            tasks=[],
        )


def test_result_defaults():
    result = TaskResult(
        task_id="task-001",
        status=TaskStatus.SUCCESS.value,
    )
    assert result.verification_status == VerificationStatus.NOT_CHECKED


def test_plan_default_status():
    plan = ExecutionPlan(
        plan_id="plan-001",
        request_id="req-001",
        tasks=[Task(task_id="task-001", action="search_files")],
    )
    assert plan.status == PlanStatus.DRAFT
