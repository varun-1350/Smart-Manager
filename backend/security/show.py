from __future__ import annotations

import os
from pathlib import Path

from .config import load_config
from .errors import SecurityError
from .pathutil import same_path


def describe(path: Path) -> str:
    if not path.exists():
        return "MISSING (nothing to access here)"
    real = Path(os.path.realpath(path))
    if not same_path(path, real):
        return f"REDIRECTED to {real} (will be refused: links aren't followed)"
    return "ok"


def main() -> int:
    try:
        cfg = load_config()
    except SecurityError as exc:
        print(exc)
        return 1
    print("Allowed:")
    for root in cfg.allowed_roots:
        print(f"  {root}   {describe(root)}")
    print(f"\nStarting folder for 'list files': {cfg.default_scope}")
    print("\nAlways protected:")
    for p in cfg.protected_paths:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())