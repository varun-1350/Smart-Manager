import asyncio
import logging
from typing import Optional, Dict, Any, Callable, Awaitable
from agent.context import TaskContext, ActionObservation
from agent.model import OllamaClient, AgentStepDecision
from agent.planner import Planner
from execution.action_dispatcher import ActionDispatcher
from config import settings

logger = logging.getLogger("smart_manager.runtime")


class AgentRuntime:
    """
    Core autonomous agent runtime executing the Observe-Plan-Act-Verify loop.
    """

    def __init__(self, client: Optional[OllamaClient] = None):
        self.client = client or OllamaClient()
        self.planner = Planner(self.client)
        self.active_contexts: Dict[str, TaskContext] = {}

    async def run_task(
        self,
        task_id: str,
        goal: str,
        conversation_id: str = "default",
        max_iterations: Optional[int] = None,
        on_step_update: Optional[Callable[[TaskContext, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> TaskContext:
        ctx = TaskContext(
            task_id=task_id,
            conversation_id=conversation_id,
            goal=goal,
            max_iterations=max_iterations or settings.agent_max_iterations,
        )
        self.active_contexts[task_id] = ctx

        logger.info(f"Starting task '{task_id}': '{goal}'")

        while not ctx.is_bounded():
            # 1. PLAN: Determine the next step using model reasoning
            try:
                decision = await self.planner.plan_step(ctx)
            except Exception as e:
                ctx.status = "failed"
                ctx.error = f"Planning failed: {str(e)}"
                if on_step_update:
                    await on_step_update(ctx, {"event": "error", "message": ctx.error})
                return ctx

            # Record step in context history
            step_record = ctx.add_step(
                thought_summary=decision.summary,
                proposed_actions=decision.actions,
            )

            # Check if model requested clarification
            if decision.clarification_question:
                ctx.status = "waiting_clarification"
                ctx.final_result = decision.clarification_question
                if on_step_update:
                    await on_step_update(ctx, {"event": "clarification", "question": decision.clarification_question})
                return ctx

            # Check if model declared the task complete
            if decision.is_complete:
                ctx.status = "completed"
                ctx.final_result = decision.final_answer or decision.summary
                if on_step_update:
                    await on_step_update(ctx, {"event": "completed", "result": ctx.final_result})
                return ctx

            # If no actions were proposed and not complete
            if not decision.actions:
                # Agent didn't propose actions but didn't finish
                ctx.status = "completed"
                ctx.final_result = decision.final_answer or decision.summary
                return ctx

            # 2. ACT & OBSERVE: Execute each proposed action
            for act in decision.actions:
                # Execute action through ActionDispatcher
                observation = ActionDispatcher.execute(
                    tool=act.tool,
                    parameters=act.parameters,
                    is_pre_approved=False,
                )

                ctx.record_observation(observation)

                # Check if action required user approval
                if "WAITING_APPROVAL" in (observation.error or ""):
                    ctx.status = "waiting_approval"
                    ctx.pending_approval = {
                        "task_id": task_id,
                        "tool": act.tool,
                        "parameters": act.parameters,
                        "reason": observation.error,
                        "risk_level": observation.verification_notes or "high",
                    }
                    if on_step_update:
                        await on_step_update(ctx, {"event": "waiting_approval", "approval": ctx.pending_approval})
                    return ctx

                if on_step_update:
                    await on_step_update(ctx, {"event": "action_executed", "observation": observation.model_dump()})

                # If an action failed, stop this batch and re-plan in the next iteration
                if not observation.success:
                    logger.warning(f"Action {act.tool} failed: {observation.error}. Re-planning...")
                    break

        # Max iterations reached without completion
        if ctx.status == "running":
            ctx.status = "failed"
            ctx.error = f"Task reached maximum iteration limit ({ctx.max_iterations}) without verifying goal completion."
            ctx.final_result = "Task exceeded iteration limit. Some actions may have been completed, but final verification could not be established."

        return ctx

    async def resume_task_approval(
        self,
        task_id: str,
        approved: bool,
        on_step_update: Optional[Callable[[TaskContext, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> TaskContext:
        ctx = self.active_contexts.get(task_id)
        if not ctx or not ctx.pending_approval:
            raise KeyError(f"No pending approval found for task {task_id}")

        pending = ctx.pending_approval
        ctx.pending_approval = None

        if not approved:
            # User rejected the action: record rejection observation so agent can adapt or abort
            obs = ActionObservation(
                tool=pending["tool"],
                parameters=pending["parameters"],
                success=False,
                error="USER_REJECTED: The user denied permission to execute this action.",
                verified=False,
            )
            ctx.record_observation(obs)
            ctx.status = "running"
        else:
            # User approved: execute with pre-approval granted
            obs = ActionDispatcher.execute(
                tool=pending["tool"],
                parameters=pending["parameters"],
                is_pre_approved=True,
            )
            ctx.record_observation(obs)
            ctx.status = "running"

        # Resume the agent loop
        return await self._continue_task(ctx, on_step_update)

    async def _continue_task(
        self,
        ctx: TaskContext,
        on_step_update: Optional[Callable[[TaskContext, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> TaskContext:
        while not ctx.is_bounded():
            decision = await self.planner.plan_step(ctx)
            step_record = ctx.add_step(
                thought_summary=decision.summary,
                proposed_actions=decision.actions,
            )

            if decision.is_complete:
                ctx.status = "completed"
                ctx.final_result = decision.final_answer or decision.summary
                return ctx

            if not decision.actions:
                ctx.status = "completed"
                ctx.final_result = decision.final_answer or decision.summary
                return ctx

            for act in decision.actions:
                obs = ActionDispatcher.execute(tool=act.tool, parameters=act.parameters)
                ctx.record_observation(obs)

                if "WAITING_APPROVAL" in (obs.error or ""):
                    ctx.status = "waiting_approval"
                    ctx.pending_approval = {
                        "task_id": ctx.task_id,
                        "tool": act.tool,
                        "parameters": act.parameters,
                        "reason": obs.error,
                    }
                    return ctx

                if not obs.success:
                    break

        return ctx
