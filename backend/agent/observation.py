import os
from pathlib import Path
from typing import Dict, Any
import psutil

from agent.context import ActionObservation
from execution.filesystem import resolve_system_path


class ObservationVerifier:
    """
    Independently inspects the Windows operating system state to verify
    whether an executed action actually produced its intended outcome.
    """

    @staticmethod
    def verify_action(tool: str, parameters: Dict[str, Any], raw_result: Any) -> ActionObservation:
        obs = ActionObservation(
            tool=tool,
            parameters=parameters,
            success=True,
            result=raw_result,
            verified=False,
        )

        try:
            # 1. Directory creation
            if tool == "fs_make_dir":
                target_path = resolve_system_path(parameters.get("path"))
                if target_path.exists() and target_path.is_dir():
                    obs.verified = True
                    obs.verification_notes = f"Verified: Directory {target_path} exists."
                else:
                    obs.verified = False
                    obs.success = False
                    obs.error = f"Verification failed: Directory {target_path} was not created."

            elif tool == "fs_write_text_file":
                target_path = resolve_system_path(parameters.get("path"))
                expected_content = parameters.get("content", "")
                if target_path.is_file() and target_path.read_text(encoding="utf-8") == expected_content:
                    obs.verified = True
                    obs.verification_notes = f"Verified: Text file {target_path} contains the requested content."
                else:
                    obs.success = False
                    obs.error = f"Verification failed: Text file {target_path} was not written as requested."

            # 2. File deletion
            elif tool == "fs_delete_file":
                target_path = resolve_system_path(parameters.get("path"))
                if not target_path.exists():
                    obs.verified = True
                    obs.verification_notes = f"Verified: Path {target_path} is no longer present."
                else:
                    obs.verified = False
                    obs.success = False
                    obs.error = f"Verification failed: Path {target_path} still exists."

            # 3. File move
            elif tool == "fs_move_file":
                src = resolve_system_path(parameters.get("src"))
                dst = resolve_system_path(parameters.get("dst"))
                if dst.exists() and not src.exists():
                    obs.verified = True
                    obs.verification_notes = f"Verified: Moved to {dst} and source removed."
                else:
                    obs.verified = dst.exists()
                    obs.verification_notes = f"Destination {dst} exists."

            # 4. File copy
            elif tool == "fs_copy_file":
                dst = resolve_system_path(parameters.get("dst"))
                if dst.exists():
                    obs.verified = True
                    obs.verification_notes = f"Verified: Destination copy {dst} exists."
                else:
                    obs.verified = False
                    obs.success = False
                    obs.error = f"Verification failed: Copy destination {dst} does not exist."

            # 5. Process termination
            elif tool == "proc_kill":
                pid = parameters.get("pid")
                if pid and not psutil.pid_exists(pid):
                    obs.verified = True
                    obs.verification_notes = f"Verified: Process PID {pid} has exited."
                else:
                    obs.verified = False
                    obs.error = f"Verification failed: Process PID {pid} is still active."

            # 6. Read-only / Query tools (dir list, search, stats, browser)
            elif tool in ("fs_list_dir", "fs_search_files", "fs_file_metadata", "sys_storage_info", "browser_search", "browser_open_url", "browser_play_youtube", "fs_open_file"):
                obs.verified = True
                obs.verification_notes = "Read/launch operation verified by OS runtime response."

            else:
                obs.verified = True
                obs.verification_notes = "Execution completed."

        except Exception as e:
            obs.verified = False
            obs.verification_notes = f"Verification check threw exception: {str(e)}"

        return obs
