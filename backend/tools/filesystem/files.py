from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Callable

from backend.security.pathutil import is_within, same_path

from .common import ToolError, ToolResult, require_abs, sha256_file


def _silent_remove(path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _different_volume(a, b) -> bool:
    return (os.path.splitdrive(os.path.abspath(a))[0].casefold()
            != os.path.splitdrive(os.path.abspath(b))[0].casefold())


# ------------------------------------------------------------------- create
def create_folder(path) -> ToolResult:
    path = require_abs(path)
    if os.path.lexists(path):
        raise ToolError(f"'{path}' already exists.")
    if not path.parent.is_dir():
        raise ToolError(f"The folder '{path.parent}' doesn't exist.")   # never makedirs
    try:
        os.mkdir(path)
    except OSError as exc:
        raise ToolError(f"Couldn't create the folder: {exc}") from exc
    if not path.is_dir():
        raise ToolError("The folder was not created.")
    return ToolResult("create_folder", f"Created folder {path}", {"path": str(path)},
                      undo={"op": "remove_empty_folder", "path": str(path)})


def create_text_file(path) -> ToolResult:
    path = require_abs(path)
    if os.path.lexists(path):
        raise ToolError(f"'{path}' already exists.")
    if not path.parent.is_dir():
        raise ToolError(f"The folder '{path.parent}' doesn't exist.")
    try:
        with open(path, "x", encoding="utf-8"):     # "x" = fail if it exists: never overwrites
            pass
    except OSError as exc:
        raise ToolError(f"Couldn't create the file: {exc}") from exc
    if not path.is_file() or path.stat().st_size != 0:
        raise ToolError("The file was not created correctly.")
    return ToolResult("create_text_file", f"Created file {path}", {"path": str(path)},
                      undo={"op": "remove_empty_file", "path": str(path)})


# --------------------------------------------------------------- move/rename
def _copy_across_volumes(src: Path, dst: Path, is_file: bool) -> None:
    """Copy to a temp name, verify by hash, rename into place, then delete the original."""
    if not is_file:
        raise ToolError("Moving a folder to another drive isn't supported yet.")
    part = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.part")
    try:
        shutil.copy2(src, part)
        if sha256_file(part) != sha256_file(src):
            raise ToolError("The copy didn't match the original, so I stopped. "
                            "Nothing was removed.")
        os.rename(part, dst)
    except ToolError:
        _silent_remove(part)
        raise
    except OSError as exc:
        _silent_remove(part)
        raise ToolError(f"Couldn't copy '{src.name}' to the other drive: {exc}") from exc
    try:
        os.remove(src)
    except OSError as exc:
        raise ToolError("Copied to the new place, but couldn't delete the original.",
                        partial={"copied_to": str(dst), "original": str(src)}) from exc


def _verify_move(src: Path, dst: Path, size: int | None, case_only: bool) -> None:
    if case_only:
        if dst.name not in os.listdir(dst.parent):
            raise ToolError("The new name didn't take effect.")
        return
    if os.path.lexists(src):
        raise ToolError("The original is still there after the move.",
                        partial={"source": str(src), "destination": str(dst)})
    if not os.path.lexists(dst):
        raise ToolError("The destination doesn't exist after the move.")
    if size is not None and dst.stat().st_size != size:
        raise ToolError("The moved file has a different size than the original.",
                        partial={"destination": str(dst)})


def move_path(src, dst, *, action: str = "move_file",
              rename: Callable = os.rename) -> ToolResult:
    """Move or rename. Never overwrites. `rename` is an injection point for tests."""
    src, dst = require_abs(src), require_abs(dst)
    if not os.path.lexists(src):
        raise ToolError(f"'{src}' doesn't exist.")
    case_only = same_path(src, dst) and src.name != dst.name       # a.txt -> A.txt
    if same_path(src, dst) and not case_only:
        raise ToolError("The source and the destination are the same.")
    if os.path.lexists(dst) and not case_only:
        raise ToolError(f"'{dst}' already exists. I won't overwrite it.")
    if not dst.parent.is_dir():
        raise ToolError(f"The folder '{dst.parent}' doesn't exist.")
    if not case_only and src.is_dir() and is_within(dst, src):
        raise ToolError("A folder can't be moved into itself.")

    is_file = src.is_file()
    size = src.stat().st_size if is_file else None
    try:
        rename(src, dst)
    except OSError as exc:
        if not _different_volume(src, dst):
            raise ToolError(f"Couldn't move '{src.name}': {exc}") from exc
        _copy_across_volumes(src, dst, is_file)
    _verify_move(src, dst, size, case_only)
    return ToolResult(action, f"Moved {src} -> {dst}",
                      {"source": str(src), "destination": str(dst)},
                      undo={"op": "move_back", "from": str(dst), "to": str(src)})


# ------------------------------------------------------------- recycle bin
def _is_fixed_drive(path: str) -> bool:
    if os.name != "nt":
        return True
    import ctypes
    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    return ctypes.windll.kernel32.GetDriveTypeW(root) == 3           # DRIVE_FIXED


def _send2trash(path: str) -> None:
    if not _is_fixed_drive(path):
        raise ToolError("This drive may not have a Recycle Bin, and I won't risk a "
                        "permanent delete.")
    try:
        from send2trash import send2trash
    except ImportError:
        raise ToolError("The 'send2trash' package isn't installed. "
                        "Run: pip install send2trash") from None
    send2trash(path)


def move_to_recycle_bin(path, *, trash: Callable[[str], None] | None = None) -> ToolResult:
    path = require_abs(path)
    if not os.path.lexists(path):
        raise ToolError(f"'{path}' doesn't exist.")
    try:
        (trash or _send2trash)(str(path))
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Couldn't move '{path.name}' to the Recycle Bin: {exc}") from exc
    if os.path.lexists(path):
        raise ToolError(f"'{path.name}' is still there after moving it to the Recycle Bin.")
    return ToolResult("move_to_recycle_bin", f"Moved {path} to the Recycle Bin",
                      {"path": str(path)},
                      undo={"op": "restore_from_recycle_bin", "path": str(path), "manual": True})