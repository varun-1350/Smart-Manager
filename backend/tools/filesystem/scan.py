from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable

MAX_RESULTS = 500
MAX_VISITED = 100_000

FILE_TYPE_EXTENSIONS = {
    "pdf": {".pdf"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"},
    "document": {".doc", ".docx", ".odt", ".rtf"},
    "spreadsheet": {".xls", ".xlsx", ".csv", ".ods"},
    "presentation": {".ppt", ".pptx", ".odp"},
    "text": {".txt", ".md", ".log"},
    "video": {".mp4", ".mkv", ".avi", ".mov", ".wmv"},
    "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
    "archive": {".zip", ".rar", ".7z"},
}

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_LINK_TAGS = {getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C),
              getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)}   # symlink, junction


@dataclass(frozen=True)
class FileInfo:
    path: str
    name: str
    is_dir: bool
    size: int
    modified: float
    created: float


@dataclass
class ScanResult:
    items: list[FileInfo] = field(default_factory=list)
    truncated: bool = False      # more matches existed than we are willing to return


class _TooMany(Exception):
    pass


def is_link(st: os.stat_result) -> bool:
    """Symlinks and junctions. Cloud placeholders (OneDrive) are other reparse types, so
    they are NOT treated as links."""
    if stat.S_ISLNK(st.st_mode):
        return True
    if getattr(st, "st_file_attributes", 0) & _REPARSE:
        return getattr(st, "st_reparse_tag", 0) in _LINK_TAGS
    return False


def _extensions(file_types) -> set[str] | None:
    if not file_types:
        return None
    exts: set[str] = set()
    for kind in file_types:
        exts |= FILE_TYPE_EXTENSIONS.get(kind, set())
    return exts                  # an unknown type gives an empty set, which matches nothing


def _in_range(st: os.stat_result, df: dict) -> bool:
    ts = getattr(st, "st_birthtime", st.st_ctime) if df["field"] == "created" else st.st_mtime
    day = datetime.fromtimestamp(ts).date()
    if df.get("start") and day < date.fromisoformat(df["start"]):
        return False
    if df.get("end") and day >= date.fromisoformat(df["end"]):
        return False
    return True


def _matches(name, is_dir, st, exts, wanted_files, wanted_names, df) -> bool:
    if exts is not None and (is_dir or os.path.splitext(name)[1].lower() not in exts):
        return False
    if wanted_files or wanted_names:
        cf = name.casefold()
        if not (cf in wanted_files or any(n in cf for n in wanted_names)):
            return False
    return df is None or _in_range(st, df)


def scan(root: Path, *, recursive: bool, filenames=(), names=(), file_types=(),
         date_filter: dict | None = None,
         is_protected: Callable[[str], bool] = lambda path: False) -> ScanResult:
    """Read-only. Never follows links/junctions and skips protected folders, so every
    result is inside `root`. AND between criteria, OR within one:
    filenames = exact name, names = part of the name, file_types = extension group."""
    exts = _extensions(list(file_types))
    wanted_files = {f.casefold() for f in filenames}
    wanted_names = [n.casefold() for n in names]
    items: list[FileInfo] = []
    truncated, visited, stack = False, 0, [str(root)]
    try:
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    entries = sorted(it, key=lambda e: e.name.casefold())
            except OSError:
                continue
            for entry in entries:
                visited += 1
                if visited > MAX_VISITED:
                    raise _TooMany
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if is_link(st):
                    continue
                is_dir = stat.S_ISDIR(st.st_mode)
                if is_dir and is_protected(entry.path):
                    continue
                if _matches(entry.name, is_dir, st, exts, wanted_files, wanted_names, date_filter):
                    if len(items) >= MAX_RESULTS:
                        raise _TooMany
                    items.append(FileInfo(entry.path, entry.name, is_dir, st.st_size,
                                          st.st_mtime, getattr(st, "st_birthtime", st.st_ctime)))
                if is_dir and recursive:
                    stack.append(entry.path)
    except _TooMany:
        truncated = True
    items.sort(key=lambda i: i.path.casefold())      # stable order, so the digest is stable
    return ScanResult(items, truncated)