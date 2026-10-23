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
5. Location & Drive Targeting:
   - When the user asks for Desktop, use path="Desktop" (Smart Manager automatically handles OneDrive desktop redirection).
   - When the user asks for Downloads, use fs_list_downloads() or path="Downloads".
   - When the user specifies a particular drive (e.g. 'in D drive', 'D:\\Downloads'), direct file operations to that drive/path (e.g. fs_list_dir(path='D:\\Downloads'), fs_list_downloads(drive='D'), or fs_search_files(path='D:\\', pattern='*Litrature*')) rather than defaulting to C:.
6. When searching for files, use broad wildcard patterns (e.g. pattern='*Litrature*') to account for spacing or spelling differences.
7. After a search or directory listing, copy the exact returned path into every follow-up action. Never reconstruct, shorten, or correct a filename yourself. If an exact match was not found, do not delete a similarly named file without first identifying its exact returned path.
8. For creating or editing a text file, ALWAYS use fs_write_text_file and request confirmation before modifying an existing file.
9. FAST COMPLETION: When proposing a terminal action that fulfills the user request (such as fs_open_file, proc_launch, browser_open_url, browser_play_youtube), or when your proposed action accomplishes the goal, you CAN set "is_complete: true" and provide "final_answer" in the SAME step. Smart Manager executes your action first and will complete immediately upon success.
10. Return your response ONLY as valid JSON matching the schema.

AVAILABLE TOOLS & SIGNATURES:
- fs_list_dir(path: str): List files and directories at path (e.g. path="Desktop" or path="D:\\Downloads").
- fs_file_metadata(path: str): Get size, dates, and extension of a file or folder.
- fs_search_files(path: str, pattern: str, recursive: bool, max_results: int): Find files matching a pattern (e.g. path="Desktop", pattern="*Notes*").
- fs_make_dir(path: str): Create a directory.
- fs_write_text_file(path: str, content: str, overwrite: bool): Create a UTF-8 text file. Do not set overwrite=true unless the user explicitly asked to replace an existing file.
- fs_copy_file(src: str, dst: str): Copy file or directory.
- fs_move_file(src: str, dst: str): Move or organize file/directory.
- fs_rename_file(path: str, new_name: str): Rename file or folder.
- fs_delete_file(path: str): Delete file or directory (requires user approval).
- fs_open_file(path: str): Open file or folder in default Windows application.
- fs_read_text_file(path: str, max_chars: int): Read text from file.
- fs_list_downloads(limit: int, drive: str, path: str): List most recent files in Downloads folder (supports drive="D" or custom path).
- proc_list(filter_name: str, limit: int): List running processes.
- proc_info(pid: int): Get process details.
- proc_launch(target: str, args: list): Launch an application or game (e.g. target="notepad", "Asphalt Legends Unite").
- proc_kill(pid: int): Terminate a running process (requires user approval).
- sys_storage_info(): View drives (C:, D:) and disk usage statistics.
- browser_search(query: str): Open browser and search on Google.
- browser_open_url(url: str): Open a specific website in the browser.
- browser_play_youtube(query: str): Open browser and play/search YouTube content.
"""


from config import settings


class Planner:
    def __init__(self, client: Any):
        self.client = client

    async def plan_step(self, context: TaskContext) -> AgentStepDecision:
        history_text = context.format_recent_history_for_prompt(max_steps=settings.agent_history_steps)

        user_prompt = f"""USER GOAL: {context.goal}

CURRENT ITERATION: {context.iteration + 1} of {context.max_iterations}

TASK EXECUTION HISTORY:
{history_text}

STRATEGY TIPS:
- When searching on Desktop, use path="Desktop" (e.g. fs_search_files(path="Desktop", pattern="*Cat*") or fs_list_dir(path="Desktop")).
- When searching for a specific file by name, use fs_search_files(path="...", pattern="*name*") with wildcards instead of fs_list_dir.
- If previous action(s) located the file, open it with fs_open_file(path="...").
- For deletion, use the exact full path returned by a previous search or listing; a waiting-approval response means the deletion has NOT happened yet.
- To create a .txt file, use fs_write_text_file with the requested path and content. It will require user confirmation before writing.
- When proposing an opening or launching action (fs_open_file, proc_launch, browser_open_url, browser_play_youtube), you can set is_complete=true and specify final_answer in the same step for instant completion.
- If the requested action was completed, mark is_complete=true with final_answer.

Determine the next decision. Propose concrete actions to advance the goal, ask for clarification if ambiguous, or mark is_complete=true with final_answer if the goal is accomplished.
Remember: return ONLY valid JSON."""

        decision = await self.client.generate_structured(
            prompt=user_prompt,
            response_model=AgentStepDecision,
            system=SYSTEM_PROMPT,
            # Grammar-constrained JSON normally succeeds on the first pass.
            # One retry preserves recovery while avoiding repeated 60-second
            # waits on a malformed local-model response.
            retries=1,
        )

        return decision
