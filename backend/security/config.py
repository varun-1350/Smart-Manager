from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import SecurityError
from .pathutil import is_within

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


def default_config(home=None, project_root=None, extra_roots=()) -> SecurityConfig:
    home = Path(home) if home else Path.home()
    project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    known = {name: home / name for name in KNOWN_FOLDER_NAMES}
    roots = [*known.values(), *(Path(r) for r in extra_roots)]
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
    _validate_roots(roots, protected)
    return SecurityConfig(allowed_roots=tuple(roots), protected_paths=tuple(protected),
                          default_scope=known["Downloads"])


def load_config(path=None, home=None) -> SecurityConfig:
    """Defaults plus extra folders from data/security.json. A broken file is an error,
    never a silent fallback."""
    project_root = Path(__file__).resolve().parents[2]
    path = Path(path) if path else project_root / "data" / "security.json"
    extra: list = []
    if path.exists():
        try:
            extra = json.loads(path.read_text(encoding="utf-8")).get("allowed_roots", [])
            if not isinstance(extra, list) or not all(isinstance(x, str) for x in extra):
                raise ValueError("'allowed_roots' must be a list of folder paths")
        except (OSError, ValueError, AttributeError) as exc:
            raise SecurityError(f"Could not read {path}: {exc}") from exc
    return default_config(home=home, project_root=project_root, extra_roots=extra)

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