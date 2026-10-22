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
    provider: Optional[str] = None

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

    @staticmethod
    def _format_observation_result(tool: str, result: Any) -> str:
        if not isinstance(result, dict):
            res_str = str(result)
            return res_str[:400] + "..." if len(res_str) > 400 else res_str

        # Smart summarization for filesystem listings
        if tool in ("fs_list_downloads", "fs_list_dir"):
            entries = result.get("entries", [])
            path = result.get("downloads_path") or result.get("path") or ""
            names = [e.get("name", "") for e in entries if isinstance(e, dict)][:15]
            names_summary = ", ".join(names)
            return f"Found {len(entries)} items in '{path}': [{names_summary}]"

        if tool == "fs_search_files":
            results = result.get("results", [])
            total = result.get("total_found", len(results))
            pattern = result.get("pattern", "")
            paths = [r.get("path", "") for r in results if isinstance(r, dict)][:10]
            paths_summary = ", ".join(paths)
            return f"Found {total} files matching '{pattern}': [{paths_summary}]"

        if tool == "fs_open_file":
            return f"Opened file: {result.get('path', 'success')}"

        if tool == "proc_launch":
            return f"Launched: {result.get('target', '')} (PID: {result.get('pid', 'N/A')})"

        res_str = str(result)
        return res_str[:400] + "..." if len(res_str) > 400 else res_str

    def format_recent_history_for_prompt(self, max_steps: int = 4) -> str:
        """Formats the last N steps and observations concisely for the agent's prompt."""
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
                        lines.append(f"Observation: {self._format_observation_result(obs.tool, obs.result)}")
                    if obs.error:
                        lines.append(f"Error: {obs.error}")
            else:
                lines.append("Actions: Pending execution")
        return "\n".join(lines)
