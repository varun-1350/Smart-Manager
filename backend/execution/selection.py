from __future__ import annotations

from pathlib import Path

from backend.security.pathutil import norm
from backend.tools.filesystem.scan import FileInfo


class SelectionError(Exception):
    """A reference like 'the largest' can't be resolved safely. The message is user-facing."""


_KEYS = {
    "largest": (lambda i: i.size, max),
    "smallest": (lambda i: i.size, min),
    "newest": (lambda i: i.modified, max),
    "oldest": (lambda i: i.modified, min),
}


def select(items: list[FileInfo], truncated: bool, mode: str,
           excluded: set[str]) -> list[FileInfo]:
    """Pick files from search results. Ties, empty results and truncated results are
    refused, never guessed. `excluded` = normalized paths already taken by earlier steps."""
    if truncated:
        raise SelectionError("Too many files matched, so I can't tell which is which. "
                             "Please narrow the search.")
    pool = [i for i in items if norm(i.path) not in excluded] if mode == "remaining" else list(items)
    if not pool:
        raise SelectionError("Nothing is left after the earlier steps took their files."
                             if mode == "remaining" else "No files matched.")
    if mode in ("all", "remaining"):
        return pool
    if mode == "only":
        if len(pool) != 1:
            raise SelectionError(f"I expected exactly one match but found {len(pool)}. "
                                 "Please name the file.")
        return pool
    files = [i for i in pool if not i.is_dir]
    if not files:
        raise SelectionError(f"Only folders matched, so there is no '{mode}' file.")
    key, pick = _KEYS[mode]
    best = pick(key(i) for i in files)
    winners = [i for i in files if key(i) == best]
    if len(winners) > 1:
        names = ", ".join(Path(w.path).name for w in winners[:4])
        raise SelectionError(f"{len(winners)} files tie for {mode} ({names}). "
                             "Please name the one you mean.")
    return winners