from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .config import SecurityConfig
from .errors import SecurityError
from .pathutil import check_absolute_text, check_plain_name, is_within, norm, same_path


class PathPolicy:
    def __init__(self, config: SecurityConfig):
        self.config = config
        self._roots = tuple(Path(os.path.realpath(str(r))) for r in config.allowed_roots)
        self._protected = tuple(Path(os.path.realpath(str(p))) for p in config.protected_paths)

    # ------------------------------------------------------------ the one gate
    def check(self, path, *, mutating: bool, must_exist: bool = False) -> Path:
        """Return the real path if it is allowed, else raise SecurityError.
        The executor must call this again immediately before every change."""
        lexical = Path(os.path.abspath(str(path)))
        real = Path(os.path.realpath(str(path)))
        if not same_path(lexical, real):
            raise SecurityError(f"'{lexical}' goes through a link, shortcut or junction, "
                                "which isn't allowed.")
        root = next((r for r in self._roots if is_within(real, r)), None)
        if root is None:
            raise SecurityError(f"'{real}' is outside the folders I'm allowed to use.")
        for prot in self._protected:
            if is_within(real, prot):
                raise SecurityError(f"'{real}' is in a protected location.")
            if mutating and is_within(prot, real):
                raise SecurityError(f"'{real}' contains a protected location, "
                                    "so I can't change it.")
        if mutating and same_path(real, root):
            raise SecurityError(f"'{real}' is one of your main folders. I can change what's "
                                "inside it, not the folder itself.")
        if must_exist and not real.exists():
            raise SecurityError(f"'{real}' doesn't exist.")
        return real

    # ------------------------------------------------------- finding by name
    def _find_by_name(self, name: str, *, folder: bool) -> Path:
        """A bare name matches the top level of an allowed folder, and must match once."""
        check_plain_name(name)
        key = name.casefold()
        hits: dict[str, Path] = {}
        for root in self._roots:
            options = [root] if root.name.casefold() == key else []
            options.append(root / name)
            for cand in options:
                if cand.exists() and (cand.is_dir() or not folder):
                    hits[norm(cand)] = cand
        kind = "a folder" if folder else "a file or folder"
        if not hits:
            raise SecurityError(f"I can't find {kind} called '{name}' in your allowed "
                                "folders. Please give its full path.")
        if len(hits) > 1:
            where = ", ".join(str(p) for p in hits.values())
            raise SecurityError(f"'{name}' matches more than one place ({where}). "
                                "Please give the full path.")
        return next(iter(hits.values()))

    # ------------------------------------------------------------- resolvers
    def resolve_folder(self, spec: dict | None, planned: Mapping[str, Path] | None = None) -> Path:
        """A folder to read from or write into. `planned` holds folders that earlier
        tasks in the same plan will create."""
        planned = planned or {}
        if spec is None:
            path = self.config.default_scope
        elif set(spec) == {"path"}:
            path = Path(check_absolute_text(spec["path"]))
        elif set(spec) == {"name"}:
            name = check_plain_name(spec["name"], "folder name")
            hits = [p for p in planned.values() if p.name.casefold() == name.casefold()]
            if len(hits) > 1:
                raise SecurityError(f"'{name}' is created more than once in this plan.")
            path = hits[0] if hits else self._find_by_name(name, folder=True)
        else:
            raise SecurityError("I don't understand which folder you mean.")
        will_exist_later = norm(path) in planned
        real = self.check(path, mutating=False, must_exist=not will_exist_later)
        if real.exists() and not real.is_dir():
            raise SecurityError(f"'{real}' isn't a folder.")
        return real

    def resolve_existing(self, item: dict, *, mutating: bool) -> Path:
        """An existing file/folder the user named: {'path': ...} or {'filename'/'name': ...}."""
        if set(item) == {"path"}:
            path = Path(check_absolute_text(item["path"]))
        elif len(item) == 1 and set(item) <= {"filename", "name"}:
            path = self._find_by_name(next(iter(item.values())), folder=False)
        else:
            raise SecurityError("I don't understand which file you mean.")
        return self.check(path, mutating=mutating, must_exist=True)

    def resolve_new(self, params: dict, planned: Mapping[str, Path] | None = None) -> Path:
        """Where a NEW file/folder would be created. It must not already exist."""
        if "path" in params:
            full = Path(check_absolute_text(params["path"]))
            name = check_plain_name(full.name, "name")
            parent = self.resolve_folder({"path": str(full.parent)}, planned)
        else:
            name = check_plain_name(params["name"], "name")
            parent = self.resolve_folder(params.get("parent"), planned)
        target = self.check(parent / name, mutating=True)
        if target.exists():
            raise SecurityError(f"'{target}' already exists.")
        return target