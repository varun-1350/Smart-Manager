import os
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Set
from pydantic import BaseModel


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ActionPermission(BaseModel):
    allowed: bool
    risk_level: RiskLevel
    requires_approval: bool
    reason: str


class SecurityPolicy:
    """
    Strict security policy enforcing path validation, destructive action gates,
    and parameter verification before any OS action is dispatched.
    """

    # Protected system paths that the agent is strictly prohibited from modifying
    PROTECTED_SYSTEM_DIRECTORIES: Set[str] = {
        os.path.normpath("C:\\Windows").lower(),
        os.path.normpath("C:\\Windows\\System32").lower(),
        os.path.normpath("C:\\Program Files").lower(),
        os.path.normpath("C:\\Program Files (x86)").lower(),
    }

    # Actions that require explicit user confirmation
    APPROVAL_REQUIRED_TOOLS: Set[str] = {
        "fs_delete_file",
        "proc_kill",
        "shell_run_command",
    }

    @classmethod
    def evaluate_action(cls, tool: str, parameters: Dict[str, Any]) -> ActionPermission:
        # 1. Unknown tool
        known_tools = {
            "fs_list_dir",
            "fs_file_metadata",
            "fs_search_files",
            "fs_make_dir",
            "fs_copy_file",
            "fs_move_file",
            "fs_rename_file",
            "fs_delete_file",
            "fs_open_file",
            "fs_read_text_file",
            "fs_list_downloads",
            "proc_list",
            "proc_info",
            "proc_launch",
            "proc_kill",
            "sys_storage_info",
            "browser_search",
            "browser_open_url",
            "browser_play_youtube",
            "shell_run_command",
        }

        if tool not in known_tools:
            return ActionPermission(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                requires_approval=False,
                reason=f"Tool '{tool}' is not an approved Smart Manager capability.",
            )

        # 2. Check filesystem path security
        for key in ["path", "src", "dst", "directory"]:
            if key in parameters and isinstance(parameters[key], str):
                path_val = parameters[key].strip()
                # Check traversal attempts
                if ".." in path_val:
                    return ActionPermission(
                        allowed=False,
                        risk_level=RiskLevel.CRITICAL,
                        requires_approval=False,
                        reason=f"Path traversal ('..') is strictly prohibited: {path_val}",
                    )

                try:
                    resolved = Path(path_val).resolve()
                    norm_str = str(resolved).lower()

                    # Prevent modifying protected OS directories
                    if tool in ("fs_make_dir", "fs_copy_file", "fs_move_file", "fs_rename_file", "fs_delete_file"):
                        for protected in cls.PROTECTED_SYSTEM_DIRECTORIES:
                            if norm_str == protected or norm_str.startswith(protected + os.sep):
                                return ActionPermission(
                                    allowed=False,
                                    risk_level=RiskLevel.CRITICAL,
                                    requires_approval=False,
                                    reason=f"Modifying protected operating system directory '{protected}' is strictly forbidden.",
                                )
                except Exception as e:
                    return ActionPermission(
                        allowed=False,
                        risk_level=RiskLevel.HIGH,
                        requires_approval=False,
                        reason=f"Invalid path parameter: {e}",
                    )

        # 3. High-risk destructive actions requiring approval
        if tool == "fs_delete_file":
            return ActionPermission(
                allowed=True,
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                reason="File or directory deletion permanently alters the filesystem.",
            )

        if tool == "proc_kill":
            return ActionPermission(
                allowed=True,
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                reason="Terminating a running process may result in unsaved state or system interruption.",
            )

        if tool == "shell_run_command":
            cmd = parameters.get("command", "")
            # Ban destructive shell patterns
            forbidden_patterns = ["rmdir /s", "del /f", "format ", "diskpart", "reg delete", "shutdown", "takeown"]
            if any(p in cmd.lower() for p in forbidden_patterns):
                return ActionPermission(
                    allowed=False,
                    risk_level=RiskLevel.CRITICAL,
                    requires_approval=False,
                    reason=f"Forbidden shell command detected: '{cmd}'",
                )
            return ActionPermission(
                allowed=True,
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                reason="Running shell commands requires explicit user authorization.",
            )

        # 4. Safe read-only tools
        read_only_tools = {
            "fs_list_dir",
            "fs_file_metadata",
            "fs_search_files",
            "fs_read_text_file",
            "fs_list_downloads",
            "proc_list",
            "proc_info",
            "sys_storage_info",
            "browser_search",
            "browser_open_url",
            "browser_play_youtube",
            "fs_open_file",
        }

        if tool in read_only_tools:
            return ActionPermission(
                allowed=True,
                risk_level=RiskLevel.READ_ONLY,
                requires_approval=False,
                reason="Read-only or launch query.",
            )

        # 5. Low/moderate state-modifying actions (make_dir, copy, move)
        return ActionPermission(
            allowed=True,
            risk_level=RiskLevel.MODERATE,
            requires_approval=False,
            reason="State-modifying filesystem action.",
        )
