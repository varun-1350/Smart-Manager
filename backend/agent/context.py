from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from agent.model import ProposedAction


class ActionObservation(BaseModel):
    tool: str
    parameters: Dict[str, Any]
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    verified: bool = False
    verification_notes: Optional[str] = None


class StepRecord(BaseModel):
    step_number: int
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    thought_summary: str
    proposed_actions: List[ProposedAction]
    observations: List[ActionObservation] = Field(default_factory=list)
    clarification_requested: Optional[str] = None


class TaskContext(BaseModel):
    task_id: str
    conversation_id: str = "default"
    goal: str
    iteration: int = 0
    max_iterations: int = 15
    status: str = "running"  # running, waiting_approval, completed, failed, cancelled
    history: List[StepRecord] = Field(default_factory=list)
    working_memory: Dict[str, Any] = Field(default_factory=dict)
    pending_approval: Optional[Dict[str, Any]] = None
    final_result: Optional[str] = None
    error: Optional[str] = None

    def add_step(self, thought_summary: str, proposed_actions: List[ProposedAction]) -> StepRecord:
        self.iteration += 1
        record = StepRecord(
            step_number=self.iteration,
            thought_summary=thought_summary,
            proposed_actions=proposed_actions,
        )
        self.history.append(record)
        return record

    def record_observation(self, observation: ActionObservation) -> None:
        if self.history:
            self.history[-1].observations.append(observation)

    def is_bounded(self) -> bool:
        return self.iteration >= self.max_iterations

    def format_recent_history_for_prompt(self, max_steps: int = 4) -> str:
        """Formats the last N steps and observations for the agent's prompt."""
        recent_steps = self.history[-max_steps:]
        if not recent_steps:
            return "No previous actions taken in this task yet."

        lines = []
        for step in recent_steps:
            lines.append(f"--- Step {step.step_number} ---")
            lines.append(f"Plan: {step.thought_summary}")
            if step.observations:
                for obs in step.observations:
                    status = "SUCCESS" if obs.success else "FAILED"
                    lines.append(f"Action: {obs.tool}({obs.parameters}) -> {status}")
                    if obs.result is not None:
                        res_str = str(obs.result)
                        if len(res_str) > 500:
                            res_str = res_str[:500] + "... [truncated]"
                        lines.append(f"Observation: {res_str}")
                    if obs.error:
                        lines.append(f"Error: {obs.error}")
            else:
                lines.append("Actions: Pending execution")
        return "\n".join(lines)
