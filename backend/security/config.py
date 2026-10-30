from __future__ import annotations

import ctypes
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import SecurityError
from .pathutil import is_within, same_path

KNOWN_FOLDER_NAMES = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")
EDITABLE_EXTENSIONS = frozenset({".txt", ".md", ".log", ".csv"})
# Types that run code. We never open them, and never rename a file into one.
BLOCKED_EXTENSIONS = frozenset({
    ".exe", ".com", ".bat", ".cmd", ".msi", ".msp", ".scr", ".pif", ".lnk", ".url",
    ".reg", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta",
    ".jar", ".dll", ".sys", ".cpl", ".appx", ".msix",
})


@dataclass(eq=False)
class SecurityConfig:
    allowed_roots: tuple[Path, ...]
    protected_paths: tuple[Path, ...]
    default_scope: Path                      # where "list files" looks when no folder is given
    editable_extensions: frozenset[str] = EDITABLE_EXTENSIONS
    blocked_extensions: frozenset[str] = BLOCKED_EXTENSIONS
    max_edit_chars: int = 10_000


def _validate_roots(roots, protected) -> None:
    for root in roots:
        if not root.is_absolute():
            raise SecurityError(f"An allowed folder must be a full path: {root}")
        if root.parent == root:
            raise SecurityError(f"'{root}' is a whole drive. Choose a folder instead.")
        for prot in protected:
            if is_within(root, prot):
                raise SecurityError(f"'{root}' is inside a protected location.")


DRIVE_PROTECTED_NAMES = ("$RECYCLE.BIN", "System Volume Information", "Recovery", "Windows",
                         "Program Files", "Program Files (x86)", "ProgramData")
_DRIVE = re.compile(r"^([A-Za-z]):[\\/]$")
_SETTING_KEYS = frozenset({"allowed_roots", "allowed_drives",
                           "include_default_folders", "default_scope"})


def _is_fixed_drive(root: str) -> bool:
    if os.name != "nt":
        return True
    return ctypes.windll.kernel32.GetDriveTypeW(root) == 3        # DRIVE_FIXED


def _parse_drive(text) -> str:
    match = _DRIVE.match(text) if isinstance(text, str) else None
    if not match:
        raise SecurityError(f"'{text}' isn't a drive. Use a drive letter, a colon and a "
                            "backslash, like D:\\")
    return f"{match.group(1).upper()}:\\"


def build_config(home=None, project_root=None, folders=(), drives=(),
                 include_default_folders=True, default_scope=None,
                 is_fixed_drive=None) -> SecurityConfig:
    home = Path(home) if home else Path.home()
    project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    fixed = is_fixed_drive or _is_fixed_drive
    known = {name: home / name for name in KNOWN_FOLDER_NAMES}

    folder_roots = [*(known.values() if include_default_folders else ()),
                    *(Path(f) for f in folders)]
    drive_roots = []
    for d in drives:
        root = _parse_drive(d)
        if not fixed(root):
            raise SecurityError(f"{root} isn't a fixed internal drive (it may be a USB, network "
                                "or removable drive), so I won't allow it.")
        drive_roots.append(Path(root))

    env = os.environ
    protected = [
        Path(env.get("SystemRoot", r"C:\Windows")),
        Path(env.get("ProgramFiles", r"C:\Program Files")),
        Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(env.get("ProgramData", r"C:\ProgramData")),
        home / "AppData",
        home / ".ssh",
        project_root,
    ]
    for root in drive_roots:
        protected += [root / name for name in DRIVE_PROTECTED_NAMES]

    _validate_roots(folder_roots, protected)
    roots = [*folder_roots, *drive_roots]
    if not roots:
        raise SecurityError("No folders are allowed. Add some to data/security.json.")

    if default_scope is not None:
        scope = Path(default_scope)
        if (not scope.is_absolute() or not any(is_within(scope, r) for r in roots)
                or any(is_within(scope, p) for p in protected)):
            raise SecurityError("'default_scope' must be inside an allowed folder and not in "
                                "a protected location.")
    else:
        downloads = known["Downloads"]
        scope = downloads if any(same_path(downloads, r) for r in roots) else roots[0]
    return SecurityConfig(allowed_roots=tuple(roots), protected_paths=tuple(protected),
                          default_scope=scope)


def default_config(home=None, project_root=None, extra_roots=()) -> SecurityConfig:
    return build_config(home=home, project_root=project_root, folders=extra_roots)


def _setting_list(raw: dict, key: str, path: Path) -> list:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise SecurityError(f"'{key}' in {path.name} must be a list of text values.")
    return value


def load_config(path=None, home=None, is_fixed_drive=None) -> SecurityConfig:
    """Settings from data/security.json. A broken file is an error, never a silent fallback."""
    project_root = Path(__file__).resolve().parents[2]
    path = Path(path) if path else project_root / "data" / "security.json"
    raw: dict = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))   # tolerates a BOM
        except (OSError, ValueError) as exc:
            raise SecurityError(f"Could not read {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise SecurityError(f"{path.name} must contain a JSON object.")
        unknown = sorted(set(raw) - _SETTING_KEYS)
        if unknown:
            raise SecurityError(f"Unknown setting(s) in {path.name}: {', '.join(unknown)}.")
    include_defaults = raw.get("include_default_folders", True)
    if not isinstance(include_defaults, bool):
        raise SecurityError("'include_default_folders' must be true or false.")
    scope = raw.get("default_scope")
    if scope is not None and not (isinstance(scope, str) and scope.strip()):
        raise SecurityError("'default_scope' must be a folder path.")
    return build_config(home=home, project_root=project_root,
                        folders=_setting_list(raw, "allowed_roots", path),
                        drives=_setting_list(raw, "allowed_drives", path),
                        include_default_folders=include_defaults, default_scope=scope,
                        is_fixed_drive=is_fixed_drive)
def sandbox_config(folder, home=None, project_root=None) -> SecurityConfig:
    """Allow ONE folder only. For testing with the real tools."""
    base = default_config(home=home, project_root=project_root)
    root = Path(folder)
    if not root.is_absolute():
        raise SecurityError("The sandbox must be a full path, like D:\\SmartManagerTest.")
    if not root.is_dir():
        raise SecurityError(f"The sandbox folder doesn't exist: {root}")
    _validate_roots([root], base.protected_paths)
    return SecurityConfig(allowed_roots=(root,), protected_paths=base.protected_paths,
                          default_scope=root)