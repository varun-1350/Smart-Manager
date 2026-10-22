from typing import List, Dict, Any
from agent.model import OllamaClient, AgentStepDecision
from agent.context import TaskContext

SYSTEM_PROMPT = """You are Smart Manager, an autonomous AI agent for Windows.
Your role is to plan and execute actions on the user's Windows system to accomplish their goals.

CRITICAL OPERATIONAL RULES:
1. You do NOT have magical direct access to the OS; you must invoke the approved tools below.
2. Formulate step-by-step plans dynamically. Do not guess file locations if you can search or list.
3. Every step, review what previous actions succeeded or failed. Adapt your plan based on real observations.
4. If an action fails, analyze why and try an alternative approach. NEVER repeat the exact same failed action.
5. Only set "is_complete: true" when you have verified that the user's goal has actually been fulfilled.
6. Return your response ONLY as valid JSON matching the schema.

AVAILABLE TOOLS & SIGNATURES:
- fs_list_dir(path: str): List files and directories at path.
- fs_file_metadata(path: str): Get size, dates, and extension of a file or folder.
- fs_search_files(path: str, pattern: str, recursive: bool, max_results: int): Find files matching a pattern (e.g. "Cat.png", "*.pdf").
- fs_make_dir(path: str): Create a directory.
- fs_copy_file(src: str, dst: str): Copy file or directory.
- fs_move_file(src: str, dst: str): Move or organize file/directory.
- fs_rename_file(path: str, new_name: str): Rename file or folder.
- fs_delete_file(path: str): Delete file or directory (requires user approval).
- fs_open_file(path: str): Open file or folder in default Windows application.
- fs_read_text_file(path: str, max_chars: int): Read text from file.
- fs_list_downloads(limit: int): List most recent files in user's Downloads folder.
- proc_list(filter_name: str, limit: int): List running processes.
- proc_info(pid: int): Get process details.
- proc_launch(target: str, args: list): Launch an application or game (e.g. target="notepad", "Asphalt Legends Unite").
- proc_kill(pid: int): Terminate a running process (requires user approval).
- sys_storage_info(): View drives (C:, D:) and disk usage statistics.
- browser_search(query: str): Open browser and search on Google.
- browser_open_url(url: str): Open a specific website in the browser.
- browser_play_youtube(query: str): Open browser and play/search YouTube content.
- shell_run_command(command: str): Run controlled PowerShell command (requires user approval).
"""


from config import settings


class Planner:
    def __init__(self, client: OllamaClient):
        self.client = client

    async def plan_step(self, context: TaskContext) -> AgentStepDecision:
        history_text = context.format_recent_history_for_prompt(max_steps=settings.agent_history_steps)

        user_prompt = f"""USER GOAL: {context.goal}

CURRENT ITERATION: {context.iteration + 1} of {context.max_iterations}

TASK EXECUTION HISTORY:
{history_text}

Determine the next decision. Either propose 1-3 concrete actions to advance the goal, ask for clarification if ambiguous, or mark is_complete=true with final_answer if the goal is accomplished.
Remember: return ONLY valid JSON."""

        decision = await self.client.generate_structured(
            prompt=user_prompt,
            response_model=AgentStepDecision,
            system=SYSTEM_PROMPT,
            retries=2,
        )

        return decision
