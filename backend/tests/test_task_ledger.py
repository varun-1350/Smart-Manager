from uuid import uuid4

from storage.database import init_db
from storage.tasks import TaskRepository


def test_task_ledger_records_ordered_lifecycle_events():
    init_db()
    task_id = f"ledger-test-{uuid4().hex}"
    TaskRepository.create(task_id, "ledger-test-conversation", "Inspect the task ledger")
    TaskRepository.transition(task_id, "planning", provider="local:test")
    TaskRepository.record_action(task_id, {"tool": "fs_list_dir", "success": True, "verified": True})
    TaskRepository.transition(task_id, "completed", result="Done")

    task = TaskRepository.get(task_id)
    assert task is not None
    assert task["status"] == "completed"
    assert task["provider"] == "local:test"
    assert [event["event_type"] for event in TaskRepository.events(task_id)] == [
        "task_queued", "task_planning", "action_observed", "task_completed"
    ]
