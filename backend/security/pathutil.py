from __future__ import annotations

import os
import re

from .errors import SecurityError

_ILLEGAL = re.compile(r'[<>"|?*\x00-\x1f]')
_RESERVED = frozenset({"con", "prn", "aux", "nul",
                       *(f"com{i}" for i in range(1, 10)),
                       *(f"lpt{i}" for i in range(1, 10))})
DRIVE_ABS = re.compile(r"^[A-Za-z]:[\\/]")


def norm(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def same_path(a, b) -> bool:
    return norm(a) == norm(b)


def is_within(child, root) -> bool:
    """True if child is root or inside root (case-insensitive on Windows)."""
    c, r = norm(child), norm(root)
    try:
        return os.path.commonpath([c, r]) == r
    except ValueError:          # different drives
        return False


def check_component(part: str, what: str = "name") -> None:
    if part in ("", ".", ".."):
        raise SecurityError(f"'{part}' isn't a valid {what}.")
    if part != part.rstrip(" ."):
        raise SecurityError(f"The {what} '{part}' ends with a space or a dot, "
                            "which Windows doesn't allow.")
    if part.split(".")[0].strip().lower() in _RESERVED:
        raise SecurityError(f"'{part}' is a reserved Windows device name.")


def check_plain_name(name, what: str = "name") -> str:
    """A single file/folder name: no separators, no drive, no illegal characters."""
    if not isinstance(name, str) or not name.strip():
        raise SecurityError(f"The {what} is empty.")
    if _ILLEGAL.search(name) or any(ch in name for ch in "/\\:"):
        raise SecurityError(f"The {what} '{name}' contains characters that aren't "
                            "allowed in a name.")
    check_component(name, what)
    return name


def check_absolute_text(raw) -> str:
    """A full Windows path like D:\\Work\\a.txt. Rejects UNC/device paths, '..',
    alternate data streams, reserved names and illegal characters."""
    if not isinstance(raw, str) or not raw.strip():
        raise SecurityError("The path is empty.")
    if raw.startswith(("\\\\", "//")):
        raise SecurityError("Network (UNC) and device paths aren't allowed.")
    if not DRIVE_ABS.match(raw):
        raise SecurityError("Please use a full path such as D:\\Work\\file.txt.")
    rest = raw[2:]
    if _ILLEGAL.search(rest) or ":" in rest:
        raise SecurityError(f"The path '{raw}' contains characters that aren't allowed.")
    for part in re.split(r"[\\/]+", rest):
        if part:
            check_component(part, "path part")
    return raw