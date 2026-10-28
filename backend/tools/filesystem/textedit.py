from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from .common import ToolError, ToolResult, require_abs, sha256_file

MAX_EDIT_BYTES = 1_000_000


def _silent_remove(path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _to_lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def edit_text(path, operation: str, *, text: str | None = None, old_text: str | None = None,
              new_text: str | None = None, backup_dir=None) -> ToolResult:
    """Append a line, or replace every exact occurrence of a text. Refuses anything it
    can't edit without altering the rest of the file."""
    path = require_abs(path)
    if not path.is_file():
        raise ToolError(f"'{path.name}' isn't a file.")
    if path.stat().st_size > MAX_EDIT_BYTES:
        raise ToolError(f"'{path.name}' is too large to edit safely.")
    raw = path.read_bytes()
    before = hashlib.sha256(raw).hexdigest()
    if b"\x00" in raw:
        raise ToolError(f"'{path.name}' doesn't look like a text file.")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ToolError(f"'{path.name}' isn't UTF-8 text, so I won't risk corrupting it.") from None
    crlf, lf = raw.count(b"\r\n"), raw.count(b"\n")
    if crlf and crlf != lf:
        raise ToolError(f"'{path.name}' mixes line-ending styles, so I won't edit it.")
    nl = "\r\n" if crlf else "\n"
    work = content.replace("\r\n", "\n")
    if "\r" in work:
        raise ToolError(f"'{path.name}' uses old-style line endings, so I won't edit it.")

    replacements = 0
    if operation == "append":
        if not text:
            raise ToolError("There is no text to add.")
        add = _to_lf(text)
        if work and not work.endswith("\n"):
            work += "\n"
        new_work = work + add + ("" if add.endswith("\n") else "\n")
    elif operation == "replace":
        if not old_text or new_text is None:
            raise ToolError("Replace needs the old text and the new text.")
        old, new = _to_lf(old_text), _to_lf(new_text)
        replacements = work.count(old)
        if replacements == 0:
            raise ToolError("I couldn't find that text in the file. Matching is exact, "
                            "including capital letters.")
        new_work = work.replace(old, new)
        if new_work == work:
            raise ToolError("That replacement wouldn't change anything.")
    else:
        raise ToolError(f"Unknown edit operation '{operation}'.")

    data = (new_work.replace("\n", "\r\n") if nl == "\r\n" else new_work).encode("utf-8")
    if len(data) > MAX_EDIT_BYTES:
        raise ToolError("The edited file would be too large.")

    backup_path = None
    if backup_dir is not None:
        bdir = Path(backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        backup_path = bdir / f"{before[:16]}-{path.name}.bak"
        if not backup_path.exists():
            backup_path.write_bytes(raw)
        if hashlib.sha256(backup_path.read_bytes()).hexdigest() != before:
            raise ToolError("The backup didn't match the original, so I stopped.")

    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if sha256_file(path) != before:
            raise ToolError("The file changed while I was editing it. Nothing was changed.")
        os.replace(tmp, path)
    except ToolError:
        _silent_remove(tmp)
        raise
    except OSError as exc:
        _silent_remove(tmp)
        raise ToolError(f"Couldn't save the edit: {exc}") from exc

    if path.read_bytes() != data:
        raise ToolError("The saved file doesn't match the intended content.",
                        partial={"path": str(path),
                                 "backup": str(backup_path) if backup_path else None})
    after = hashlib.sha256(data).hexdigest()
    undo = None
    if backup_path:
        undo = {"op": "restore_backup", "path": str(path), "backup": str(backup_path),
                "expected_sha256": after}
    return ToolResult("edit_text_file", f"Edited {path}",
                      {"path": str(path), "operation": operation, "replacements": replacements,
                       "before_sha256": before, "after_sha256": after,
                       "backup": str(backup_path) if backup_path else None},
                      undo=undo)