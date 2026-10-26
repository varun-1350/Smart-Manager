import time
from typing import Dict, Any, Tuple
from agent.context import ActionObservation
from agent.observation import ObservationVerifier
from security.permissions import SecurityPolicy, RiskLevel
from execution.filesystem import FilesystemOperations
from execution.processes import ProcessOperations
from execution.browser import BrowserOperations


class ActionDispatcher:
    """
    Central action execution engine. Enforces security policies, dispatches
    to approved system execution mechanisms, records timing, and verifies results.
    """

    @classmethod
    def execute(
        cls,
        tool: str,
        parameters: Dict[str, Any],
        is_pre_approved: bool = False,
    ) -> ActionObservation:
        start_time = time.perf_counter()

        # 1. Security Policy Evaluation
        permission = SecurityPolicy.evaluate_action(tool, parameters)
        if not permission.allowed:
            return ActionObservation(
                tool=tool,
                parameters=parameters,
                success=False,
                error=f"Security Policy Denied: {permission.reason}",
                verified=False,
            )

        # 2. Check if user approval is required and not granted
        if permission.requires_approval and not is_pre_approved:
            return ActionObservation(
                tool=tool,
                parameters=parameters,
                success=False,
                error=f"WAITING_APPROVAL: Action '{tool}' requires explicit user confirmation. Reason: {permission.reason}",
                verified=False,
                verification_notes=permission.risk_level.value,
            )

        # 3. Dispatch to execution modules
        raw_result = None
        error_msg = None
        success = True

        try:
            # Filesystem Operations
            if tool == "fs_list_dir":
                target_path = parameters.get("path") or parameters.get("dir") or parameters.get("directory") or "."
                raw_result = FilesystemOperations.list_dir(target_path)
            elif tool == "fs_file_metadata":
                target_path = parameters.get("path") or parameters.get("filepath") or parameters.get("target")
                raw_result = FilesystemOperations.file_metadata(target_path)
            elif tool == "fs_search_files":
                target_path = parameters.get("path") or parameters.get("search_root") or "."
                pattern = (
                    parameters.get("pattern")
                    or parameters.get("filename_pattern")
                    or parameters.get("filename")
                    or parameters.get("name")
                    or "*"
                )
                raw_result = FilesystemOperations.search_files(
                    path=target_path,
                    pattern=pattern,
                    recursive=parameters.get("recursive", True),
                    max_results=parameters.get("max_results", 50),
                )
            elif tool == "fs_make_dir":
                raw_result = FilesystemOperations.make_dir(parameters.get("path") or parameters.get("dir"))
            elif tool == "fs_write_text_file":
                raw_result = FilesystemOperations.write_text_file(
                    parameters["path"],
                    parameters["content"],
                    overwrite=parameters.get("overwrite", False),
                )
            elif tool == "fs_browse_dir":
                raw_result = FilesystemOperations.browse_directory(
                    path=parameters.get("path"),
                    sort_by=parameters.get("sort_by", "name"),
                    sort_order=parameters.get("sort_order", "asc"),
                    show_hidden=parameters.get("show_hidden", False),
                    limit=parameters.get("limit", 500),
                    offset=parameters.get("offset", 0),
                )
            elif tool == "fs_copy_file":
                raw_result = FilesystemOperations.copy_file(parameters["src"], parameters["dst"])
            elif tool == "fs_copy_files":
                raw_result = FilesystemOperations.safe_copy(
                    src_paths=parameters.get("src_paths") or parameters.get("paths", []),
                    dest_folder=parameters.get("dest_folder") or parameters.get("dst"),
                    batch_id=parameters.get("batch_id"),
                )
            elif tool == "fs_move_file":
                raw_result = FilesystemOperations.move_file(parameters["src"], parameters["dst"])
            elif tool == "fs_move_files":
                raw_result = FilesystemOperations.safe_move(
                    src_paths=parameters.get("src_paths") or parameters.get("paths", []),
                    dest_folder=parameters.get("dest_folder") or parameters.get("dst"),
                    batch_id=parameters.get("batch_id"),
                )
            elif tool == "fs_rename_file":
                raw_result = FilesystemOperations.rename_file(parameters["path"], parameters["new_name"])
            elif tool == "fs_delete_file":
                raw_result = FilesystemOperations.delete_file(parameters["path"])
            elif tool == "fs_trash_files":
                raw_result = FilesystemOperations.safe_trash(
                    paths=parameters.get("paths") or [parameters.get("path")],
                    batch_id=parameters.get("batch_id"),
                )
            elif tool == "fs_open_file":
                target_path = (
                    parameters.get("path")
                    or parameters.get("filepath")
                    or parameters.get("filename")
                    or parameters.get("file")
                    or parameters.get("target")
                )
                raw_result = FilesystemOperations.open_file(target_path)
            elif tool == "fs_read_text_file":
                target_path = parameters.get("path") or parameters.get("filepath")
                raw_result = FilesystemOperations.read_text_file(
                    target_path,
                    max_chars=parameters.get("max_chars", 5000),
                )
            elif tool == "fs_list_downloads":
                raw_result = FilesystemOperations.list_downloads(
                    limit=parameters.get("limit", 10),
                    drive=parameters.get("drive"),
                    path=parameters.get("path"),
                )

            # Process Operations
            elif tool == "proc_list":
                raw_result = ProcessOperations.list_processes(
                    filter_name=parameters.get("filter_name"),
                    limit=parameters.get("limit", 50),
                )
            elif tool == "proc_info":
                raw_result = ProcessOperations.process_info(parameters["pid"])
            elif tool == "proc_launch":
                raw_result = ProcessOperations.launch_process(
                    target=parameters["target"],
                    args=parameters.get("args"),
                )
            elif tool == "proc_kill":
                raw_result = ProcessOperations.terminate_process(parameters["pid"])
            elif tool == "sys_storage_info":
                raw_result = ProcessOperations.storage_info()

            # Browser Operations
            elif tool == "browser_search":
                raw_result = BrowserOperations.search_web(parameters["query"])
            elif tool == "browser_open_url":
                raw_result = BrowserOperations.open_url(parameters["url"])
            elif tool == "browser_play_youtube":
                raw_result = BrowserOperations.play_youtube(parameters["query"])

            else:
                success = False
                error_msg = f"No handler registered for tool '{tool}'"

        except Exception as exc:
            success = False
            error_msg = str(exc)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 4. Verify observation via ObservationVerifier
        if success:
            obs = ObservationVerifier.verify_action(tool, parameters, raw_result)
            obs.duration_ms = duration_ms
            return obs
        else:
            return ActionObservation(
                tool=tool,
                parameters=parameters,
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
                verified=False,
            )
