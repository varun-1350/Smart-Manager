import os
from urllib.parse import urlparse
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Set
from pydantic import BaseModel

from execution.filesystem import resolve_system_path


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
        "fs_trash_files",
        "fs_write_text_file",
        "fs_copy_file",
        "fs_copy_files",
        "fs_move_file",
        "fs_move_files",
        "fs_rename_file",
        "fs_make_dir",
        "proc_launch",
        "proc_kill",
    }

    MAX_PATH_LENGTH = 32_767

    @classmethod
    def _deny(cls, reason: str, risk: RiskLevel = RiskLevel.CRITICAL) -> ActionPermission:
        return ActionPermission(allowed=False, risk_level=risk, requires_approval=False, reason=reason)

    @classmethod
    def evaluate_action(cls, tool: str, parameters: Dict[str, Any]) -> ActionPermission:
        # 1. Unknown tool
        known_tools = {
            "fs_list_dir",
            "fs_browse_dir",
            "fs_file_metadata",
            "fs_search_files",
            "fs_make_dir",
            "fs_write_text_file",
            "fs_copy_file",
            "fs_copy_files",
            "fs_move_file",
            "fs_move_files",
            "fs_rename_file",
            "fs_delete_file",
            "fs_trash_files",
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
        }

        if tool not in known_tools:
            return ActionPermission(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                requires_approval=False,
                reason=f"Tool '{tool}' is not an approved Smart Manager capability.",
            )

        # 2. Check filesystem path security.  Resolve before comparing so aliases and
        # symlinks cannot be used to reach protected locations.
        all_paths_to_check = []
        for key in ["path", "src", "dst", "directory", "dest_folder"]:
            if key in parameters and isinstance(parameters[key], str):
                all_paths_to_check.append(parameters[key])
        for key in ["paths", "src_paths"]:
            if key in parameters and isinstance(parameters[key], list):
                for item in parameters[key]:
                    if isinstance(item, str):
                        all_paths_to_check.append(item)

        for path_val in all_paths_to_check:
            path_val = path_val.strip()
            if not path_val or len(path_val) > cls.MAX_PATH_LENGTH:
                return cls._deny("Path parameter is empty or exceeds the Windows path limit.", RiskLevel.HIGH)
            # Check traversal attempts
            if ".." in path_val:
                return ActionPermission(
                    allowed=False,
                    risk_level=RiskLevel.CRITICAL,
                    requires_approval=False,
                    reason=f"Path traversal ('..') is strictly prohibited: {path_val}",
                )

            try:
                resolved = resolve_system_path(path_val)
                norm_str = str(resolved).lower()

                # Prevent modifying protected OS directories
                if tool in ("fs_make_dir", "fs_write_text_file", "fs_copy_file", "fs_copy_files", "fs_move_file", "fs_move_files", "fs_rename_file", "fs_delete_file", "fs_trash_files"):
                    for protected in cls.PROTECTED_SYSTEM_DIRECTORIES:
                        if norm_str == protected or norm_str.startswith(protected + os.sep):
                            return ActionPermission(
                                allowed=False,
                                risk_level=RiskLevel.CRITICAL,
                                requires_approval=False,
                                reason=f"Modifying protected operating system directory '{protected}' is strictly forbidden.",
                            )
            except (OSError, ValueError):
                return cls._deny("Invalid filesystem path parameter.", RiskLevel.HIGH)

        if tool == "fs_rename_file":
            name = parameters.get("new_name")
            if not isinstance(name, str) or not name.strip() or len(name) > 255 or any(c in name for c in "\\\\/:") or name in {".", ".."}:
                return cls._deny("New file name must be a single valid file name.", RiskLevel.HIGH)

        if tool in {"browser_open_url"}:
            url = parameters.get("url")
            parsed = urlparse(url.strip() if isinstance(url, str) and "://" in url else f"https://{url.strip()}" if isinstance(url, str) else "")
            if not isinstance(url, str) or any(char.isspace() for char in url) or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return cls._deny("Only absolute HTTP(S) URLs may be opened.", RiskLevel.HIGH)

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

        # 5. All state-modifying actions require explicit confirmation.  This
        # prevents a compromised model from silently changing user data.
        return ActionPermission(
            allowed=True,
            risk_level=RiskLevel.MODERATE,
            requires_approval=tool in cls.APPROVAL_REQUIRED_TOOLS,
            reason="This action changes local machine state.",
        )
