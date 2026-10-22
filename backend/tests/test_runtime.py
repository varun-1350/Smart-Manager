import pytest
from unittest.mock import AsyncMock, patch
from agent.runtime import AgentRuntime
from agent.model import OllamaClient, AgentStepDecision, ProposedAction
from pathlib import Path


@pytest.mark.asyncio
async def test_agent_runtime_multi_step_execution(tmp_path: Path):
    # Setup test file
    cat_img = tmp_path / "Cat.png"
    cat_img.write_text("fake image data")

    client = OllamaClient(base_url="http://mock:11434", model="test-model")
    runtime = AgentRuntime(client=client)

    # Step 1: Model decides to search for Cat.png
    step1_decision = AgentStepDecision(
        summary="Searching for Cat.png in workspace",
        actions=[
            ProposedAction(
                tool="fs_search_files",
                parameters={"path": str(tmp_path), "pattern": "Cat.png"},
                reasoning="Find the exact path of the image",
            )
        ],
        is_complete=False,
    )

    # Step 2: Model sees search observation and completes
    step2_decision = AgentStepDecision(
        summary="Cat.png found, task completed",
        actions=[],
        is_complete=True,
        final_answer=f"Found Cat.png at {cat_img}",
    )

    with patch.object(runtime.planner, "plan_step", new_callable=AsyncMock) as mock_plan:
        mock_plan.side_effect = [step1_decision, step2_decision]

        context = await runtime.run_task(
            task_id="task-test-1",
            goal="Find Cat.png",
            conversation_id="conv-1",
        )

        assert context.status == "completed"
        assert context.iteration == 2
        assert "Found Cat.png" in context.final_result
        assert len(context.history) == 2
        # Verify first step had an observation with actual result
        obs = context.history[0].observations[0]
        assert obs.tool == "fs_search_files"
        assert obs.success is True
        assert obs.result["total_found"] == 1


@pytest.mark.asyncio
async def test_agent_runtime_approval_interruption_and_resumption(tmp_path: Path):
    target_file = tmp_path / "temp.txt"
    target_file.write_text("delete this")

    client = OllamaClient(base_url="http://mock:11434", model="test-model")
    runtime = AgentRuntime(client=client)

    # Step 1: Model proposes to delete the file
    step1_decision = AgentStepDecision(
        summary="Proposing to delete temp.txt",
        actions=[
            ProposedAction(
                tool="fs_delete_file",
                parameters={"path": str(target_file)},
                reasoning="Clean up temp file",
            )
        ],
        is_complete=False,
    )

    # Step 2 (after approval): Model completes
    step2_decision = AgentStepDecision(
        summary="Deletion verified, completing task",
        actions=[],
        is_complete=True,
        final_answer="temp.txt has been deleted successfully.",
    )

    with patch.object(runtime.planner, "plan_step", new_callable=AsyncMock) as mock_plan:
        mock_plan.side_effect = [step1_decision, step2_decision]

        # 1. Run task until approval pause
        ctx = await runtime.run_task(
            task_id="task-del-1",
            goal="Delete temp.txt",
        )
        assert ctx.status == "waiting_approval"
        assert ctx.pending_approval is not None
        assert ctx.pending_approval["tool"] == "fs_delete_file"
        assert target_file.exists()  # Not deleted yet!

        # 2. User approves the action
        resumed_ctx = await runtime.resume_task_approval(
            task_id="task-del-1",
            approved=True,
        )
        assert resumed_ctx.status == "completed"
        assert not target_file.exists()  # Now verified deleted!
