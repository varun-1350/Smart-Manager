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
from pathlib import Path
import json
from agent.model import FilePlanPreview, FileActionItem
from execution.filesystem import FilesystemOperations, resolve_system_path
from security.permissions import SecurityPolicy


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
            retries=1,
        )

        return decision

    async def plan_file_batch_task(self, folder_path: str, instruction: str) -> FilePlanPreview:
        """
        Creates a structured, inspectable batch action plan for file organization and management.
        Guarantees that risk levels are strictly computed by SecurityPolicy, never trusted from LLM.
        """
        target = resolve_system_path(folder_path)
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        browse_res = FilesystemOperations.browse_directory(str(target), limit=300)
        file_entries = [e for e in browse_res["entries"] if not e["is_dir"]]

        if not file_entries:
            return FilePlanPreview(
                summary="The target folder contains no files to organize.",
                target_folder=str(target),
                actions=[],
                skipped_files=[],
                conflicts=[],
            )

        # Category mapping for type organization
        category_folder_names = {
            "documents": "Documents",
            "spreadsheets": "Spreadsheets",
            "presentations": "Presentations",
            "images": "Images",
            "videos": "Videos",
            "audio": "Audio",
            "archives": "Archives",
            "code": "Code",
            "text": "Text Files",
            "executables": "Executables",
        }

        # Check if instruction is a standard organization request (fast & deterministic path)
        inst_lower = instruction.lower()
        use_rule_engine = any(k in inst_lower for k in ["file type", "type", "extension", "organize by type", "group by type", "categorize"])

        actions = []
        skipped = []
        conflicts = []

        if use_rule_engine or not self.client:
            # Deterministic, safe rule-based planner
            action_counter = 1
            for f in file_entries:
                cat = f.get("category", "other")
                subfolder = category_folder_names.get(cat)
                if not subfolder or cat == "other":
                    skipped.append({"file": f["name"], "reason": "Category is uncertain or miscellaneous"})
                    continue

                dest_dir = target / subfolder
                dest_file = dest_dir / f["name"]

                has_conflict = dest_file.exists()
                if has_conflict:
                    conflicts.append({
                        "source": f["path"],
                        "destination": str(dest_file),
                        "conflict": "Destination file already exists (will auto-version if approved)",
                    })

                actions.append(FileActionItem(
                    id=f"act-{action_counter}",
                    tool="fs_move_file",
                    source=f["path"],
                    destination=str(dest_file),
                    reason=f"Move {f['extension'].upper() or 'file'} into {subfolder}/ based on file type",
                    risk_level=SecurityPolicy.evaluate_action("fs_move_file", {"src": f["path"], "dst": str(dest_file)}).risk_level.value,
                    requires_approval=True,
                ))
                action_counter += 1

            summary = f"Proposed moving {len(actions)} files into categorized folders based on file type."
            if skipped:
                summary += f" Kept {len(skipped)} files unchanged due to uncertain types."

            return FilePlanPreview(
                summary=summary,
                target_folder=str(target),
                actions=actions,
                skipped_files=skipped,
                conflicts=conflicts,
            )

        # AI-Assisted Planning for custom/complex instructions
        file_summary_list = [
            {"name": f["name"], "category": f["category"], "ext": f["extension"], "size": f["size_formatted"]}
            for f in file_entries[:60]
        ]
        prompt = f"""You are Smart Manager's File Organization Specialist.
Target Directory: {str(target)}
User Goal: {instruction}

Available Files in Directory:
{json.dumps(file_summary_list, indent=1)}

Plan the appropriate file moves or renames to satisfy the user goal.
Rules:
1. Provide a concise summary of the organization strategy.
2. For each file moved, specify tool="fs_move_file", source=exact file path, destination=proposed destination path.
3. If a file does not fit or is ambiguous, list it under skipped_files with a reason.
4. Do NOT propose deleting files unless explicitly requested.
5. Return ONLY a valid JSON object matching the requested schema."""

        try:
            plan = await self.client.generate_structured(
                prompt=prompt,
                response_model=FilePlanPreview,
                system="You are an expert file organizer. Plan precise file moves and renames. Return ONLY valid JSON matching the schema.",
                retries=1,
            )
            # Recompute risk_level and requires_approval through SecurityPolicy for EVERY item
            validated_actions = []
            for act in plan.actions:
                dest = act.destination or str(target / act.source)
                sec = SecurityPolicy.evaluate_action(act.tool, {"src": act.source, "dst": dest, "path": act.source})
                dest_p = Path(dest)
                if dest_p.exists():
                    plan.conflicts.append({"source": act.source, "destination": dest, "conflict": "Target exists"})
                validated_actions.append(FileActionItem(
                    id=act.id,
                    tool=act.tool,
                    source=act.source,
                    destination=dest,
                    reason=act.reason,
                    risk_level=sec.risk_level.value,
                    requires_approval=sec.requires_approval,
                ))
            plan.actions = validated_actions
            plan.target_folder = str(target)
            return plan
        except Exception:
            # Fallback to rule engine on model failure
            return await self.plan_file_batch_task(folder_path, "organize by file type")

