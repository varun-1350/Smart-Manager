from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path


class ToolError(Exception):
    """A tool refused or failed. `partial` says what may already have changed."""

    def __init__(self, message: str, partial: dict | None = None):
        super().__init__(message)
        self.partial = partial


@dataclass(frozen=True)
class ToolResult:
    action: str
    message: str
    output: dict = field(default_factory=dict)
    verified: bool = True            # False only when success can't be checked (opening a file)
    undo: dict | None = None         # what the journal needs to reverse this


def require_abs(path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        raise ToolError(f"Expected a full path, got '{path}'.")
    return Path(os.path.abspath(p))


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()