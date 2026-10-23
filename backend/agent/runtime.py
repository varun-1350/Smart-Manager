import asyncio
import logging
import secrets
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

    def __init__(
        self,
        client: Optional[Any] = None,
        provider_manager: Optional[Any] = None,
    ):
        self.provider_manager = provider_manager
        self.client = client or (getattr(provider_manager, "local_provider", None) if provider_manager else OllamaClient())
        self.planner = Planner(self.client)
        self.active_contexts: Dict[str, TaskContext] = {}
        self.stop_requested: set[str] = set()

    def cancel_task(self, task_id: str) -> bool:
        """Signals an active task to stop immediately and halt OS actions."""
        self.stop_requested.add(task_id)
        ctx = self.active_contexts.get(task_id)
        if ctx:
            ctx.status = "cancelled"
            ctx.final_result = "Task execution was cancelled by user."
            return True
        return False

    def _retire_context(self, ctx: TaskContext) -> None:
        """Release retained state once a task can no longer be resumed."""
        if ctx.status != "waiting_approval":
            self.active_contexts.pop(ctx.task_id, None)
            if self.provider_manager:
                self.provider_manager.register_task_end(ctx.task_id)

    async def run_task(
        self,
        task_id: str,
        goal: str,
        conversation_id: str = "default",
        max_iterations: Optional[int] = None,
        on_step_update: Optional[Callable[[TaskContext, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> TaskContext:
        if task_id in self.active_contexts:
            raise ValueError("A task with this identifier is already active.")
        ctx = TaskContext(
            task_id=task_id,
            conversation_id=conversation_id,
            goal=goal,
            max_iterations=max_iterations or settings.agent_max_iterations,
        )
        self.active_contexts[task_id] = ctx

        if self.provider_manager:
            self.provider_manager.register_task_start(task_id)
            try:
                active_provider, provider_label = await self.provider_manager.get_active_provider()
                self.planner = Planner(active_provider)
                ctx.provider = provider_label
            except Exception as e:
                ctx.status = "failed"
                ctx.error = f"AI Provider Error: {str(e)}"
                ctx.final_result = ctx.error
                self._retire_context(ctx)
                return ctx
        elif hasattr(self.client, "model"):
            ctx.provider = f"local:{self.client.model}"

        logger.info(f"Starting task '{task_id}': '{goal}' using {ctx.provider}")

        try:
            while not ctx.is_bounded():
                if task_id in self.stop_requested or ctx.status == "cancelled":
                    ctx.status = "cancelled"
                    ctx.final_result = "Task execution was stopped by user."
                    return ctx

                # 1. PLAN: Determine the next step using model reasoning
                if self.provider_manager and not self.provider_manager.provider_available_for_task(ctx.provider or "unknown"):
                    ctx.status = "failed"
                    ctx.error = "AI provider is temporarily unavailable after repeated failures. Please retry shortly."
                    ctx.final_result = ctx.error
                    return ctx
                try:
                    decision = await self.planner.plan_step(ctx)
                    if self.provider_manager:
                        self.provider_manager.record_provider_success(ctx.provider or "unknown")
                except Exception as e:
                    if self.provider_manager:
                        self.provider_manager.record_provider_failure(ctx.provider or "unknown")
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

                # If no actions were proposed
                if not decision.actions:
                    ctx.status = "completed"
                    ctx.final_result = decision.final_answer or decision.summary
                    if on_step_update:
                        await on_step_update(ctx, {"event": "completed", "result": ctx.final_result})
                    return ctx

                # 2. ACT & OBSERVE: Execute each proposed action
                batch_succeeded = True
                for act in decision.actions:
                    # Execute action through ActionDispatcher
                    # Dispatch only bounded operations; the action layer caps result
                    # sizes and all potentially destructive work is paused for approval.
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
                            "description": act.reasoning,
                            "reason": observation.error,
                            "risk_level": observation.verification_notes or "high",
                            "approval_token": secrets.token_urlsafe(32),
                        }
                        if on_step_update:
                            await on_step_update(ctx, {"event": "waiting_approval", "approval": ctx.pending_approval})
                        return ctx

                    if on_step_update:
                        await on_step_update(ctx, {"event": "action_executed", "observation": observation.model_dump()})

                    # If an action failed, stop this batch and re-plan in the next iteration
                    if not observation.success:
                        logger.warning(f"Action {act.tool} failed: {observation.error}. Re-planning...")
                        batch_succeeded = False
                        break

                # Fast Completion Check:
                # If actions succeeded and either model signaled completion OR a terminal action succeeded
                terminal_tools = {
                    "fs_open_file",
                    "proc_launch",
                    "browser_open_url",
                    "browser_play_youtube",
                    "browser_search",
                }
                is_terminal = bool(decision.actions and decision.actions[-1].tool in terminal_tools)
                if batch_succeeded and (decision.is_complete or is_terminal):
                    ctx.status = "completed"
                    ctx.final_result = (
                        decision.final_answer
                        or decision.summary
                        or f"Completed {decision.actions[-1].tool} successfully."
                    )
                    if on_step_update:
                        await on_step_update(ctx, {"event": "completed", "result": ctx.final_result})
                    return ctx

            # Max iterations reached without completion
            if ctx.status == "running":
                ctx.status = "failed"
                ctx.error = f"Task reached maximum iteration limit ({ctx.max_iterations}) without verifying goal completion."
                ctx.final_result = "Task exceeded iteration limit. Some actions may have been completed, but final verification could not be established."
        finally:
            self._retire_context(ctx)
            self.stop_requested.discard(task_id)

        return ctx

    async def resume_task_approval(
        self,
        task_id: str,
        approved: bool,
        approval_token: Optional[str] = None,
        on_step_update: Optional[Callable[[TaskContext, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> TaskContext:
        ctx = self.active_contexts.get(task_id)
        if not ctx or not ctx.pending_approval:
            raise KeyError(f"No pending approval found for task {task_id}")

        pending = ctx.pending_approval
        expected_token = pending.get("approval_token")
        if not expected_token or not approval_token or not secrets.compare_digest(expected_token, approval_token):
            raise PermissionError("Approval request is invalid or has expired.")
        ctx.pending_approval = None

        if not approved:
            # A denied request cancels this task instead of proposing the same action again.
            obs = ActionObservation(
                tool=pending["tool"],
                parameters=pending["parameters"],
                success=False,
                error="USER_REJECTED: The user denied permission to execute this action.",
                verified=False,
            )
            ctx.record_observation(obs)
            ctx.status = "cancelled"
            ctx.final_result = "Action cancelled at your request."
            self._retire_context(ctx)
            return ctx
        else:
            # User approved: execute with pre-approval granted
            obs = ActionDispatcher.execute(
                tool=pending["tool"],
                parameters=pending["parameters"],
                is_pre_approved=True,
            )
            ctx.record_observation(obs)

            # Do not let a later planning step describe an approved action as
            # successful when dispatching it (or verifying it) actually failed.
            # This is particularly important for destructive operations, where a
            # misleading completion message leaves the user unsure of the state.
            if not obs.success:
                ctx.status = "failed"
                ctx.error = obs.error or f"Approved action '{pending['tool']}' failed."
                ctx.final_result = f"The approved action could not be completed: {ctx.error}"
                if on_step_update:
                    await on_step_update(ctx, {"event": "action_failed", "observation": obs.model_dump()})
                self._retire_context(ctx)
                return ctx

            ctx.status = "running"

        # Resume the agent loop
        try:
            result = await self._continue_task(ctx, on_step_update)
        except Exception as exc:
            logger.exception("Task approval continuation failed")
            ctx.status = "failed"
            ctx.error = "Planning failed after approval."
            ctx.final_result = ctx.error
            result = ctx
        self._retire_context(result)
        return result

    async def _continue_task(
        self,
        ctx: TaskContext,
        on_step_update: Optional[Callable[[TaskContext, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> TaskContext:
        while not ctx.is_bounded():
            if self.provider_manager and not self.provider_manager.provider_available_for_task(ctx.provider or "unknown"):
                ctx.status = "failed"
                ctx.error = "AI provider is temporarily unavailable after repeated failures. Please retry shortly."
                ctx.final_result = ctx.error
                return ctx
            try:
                decision = await self.planner.plan_step(ctx)
                if self.provider_manager:
                    self.provider_manager.record_provider_success(ctx.provider or "unknown")
            except Exception:
                if self.provider_manager:
                    self.provider_manager.record_provider_failure(ctx.provider or "unknown")
                raise
            step_record = ctx.add_step(
                thought_summary=decision.summary,
                proposed_actions=decision.actions,
            )

            if not decision.actions:
                ctx.status = "completed"
                ctx.final_result = decision.final_answer or decision.summary
                return ctx

            batch_succeeded = True
            for act in decision.actions:
                obs = ActionDispatcher.execute(tool=act.tool, parameters=act.parameters)
                ctx.record_observation(obs)

                if "WAITING_APPROVAL" in (obs.error or ""):
                    ctx.status = "waiting_approval"
                    ctx.pending_approval = {
                        "task_id": ctx.task_id,
                        "tool": act.tool,
                        "parameters": act.parameters,
                        "description": act.reasoning,
                        "reason": obs.error,
                        "risk_level": obs.verification_notes or "high",
                        "approval_token": secrets.token_urlsafe(32),
                    }
                    return ctx

                if not obs.success:
                    batch_succeeded = False
                    break

            terminal_tools = {
                "fs_open_file",
                "proc_launch",
                "browser_open_url",
                "browser_play_youtube",
                "browser_search",
            }
            is_terminal = bool(decision.actions and decision.actions[-1].tool in terminal_tools)
            if batch_succeeded and (decision.is_complete or is_terminal):
                ctx.status = "completed"
                ctx.final_result = (
                    decision.final_answer
                    or decision.summary
                    or f"Completed {decision.actions[-1].tool} successfully."
                )
                return ctx

        return ctx
