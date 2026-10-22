import os
import shutil
import glob
import re
import difflib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    import winreg
except ImportError:
    winreg = None


def get_special_folder(folder_name: str) -> Path:
    """Retrieve Windows special folder locations, accounting for OneDrive redirection."""
    reg_names = {
        "desktop": "Desktop",
        "documents": "Personal",
        "pictures": "My Pictures",
        "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    }
    if winreg:
        try:
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            )
            reg_key = reg_names.get(folder_name.lower(), folder_name)
            val, _ = winreg.QueryValueEx(k, reg_key)
            expanded = os.path.expandvars(str(val))
            if os.path.exists(expanded):
                return Path(expanded).resolve()
        except Exception:
            pass

    home = Path.home()
    folder_cap = folder_name.capitalize()
    for cand in [home / "OneDrive" / folder_cap, home / folder_cap, Path("C:/Users/Public") / folder_cap]:
        if cand.exists():
            return cand.resolve()

    return (home / folder_cap).resolve()


def resolve_system_path(path_str: Optional[str]) -> Path:
    """
    Smart Windows path resolver. Seamlessly handles Windows folder redirection (OneDrive Desktop),
    shorthand folder names ('Desktop', 'Documents', 'Downloads'), tilde expansion, and environment variables.
    """
    if not path_str or not str(path_str).strip():
        return get_special_folder("desktop")

    clean = str(path_str).strip(' "\'')
    clean_lower = clean.lower().replace("/", "\\")

    # 1. Shorthand user folder names
    if clean_lower in ("desktop", "~/desktop", "%desktop%", "$desktop"):
        return get_special_folder("desktop")
    if clean_lower in ("documents", "~/documents", "my documents", "%documents%"):
        return get_special_folder("documents")
    if clean_lower in ("downloads", "~/downloads", "%downloads%"):
        return get_special_folder("downloads")
    if clean_lower in ("pictures", "~/pictures", "my pictures", "%pictures%"):
        return get_special_folder("pictures")

    desktop_dir = get_special_folder("desktop")

    # 2. Check prefix like Desktop\ or desktop/
    if clean_lower.startswith("desktop\\"):
        sub = clean[8:].lstrip("\\/")
        return (desktop_dir / sub).resolve()

    # 3. Check C:\Desktop or C:/Desktop
    if clean_lower.startswith("c:\\desktop"):
        sub = clean[10:].lstrip("\\/")
        return (desktop_dir / sub).resolve() if sub else desktop_dir

    # 4. Check C:\Users\<user>\Desktop when redirection has moved it
    home_lower = str(Path.home()).lower().replace("/", "\\")
    user_desktop_prefix = f"{home_lower}\\desktop"
    if clean_lower == user_desktop_prefix:
        return desktop_dir
    if clean_lower.startswith(user_desktop_prefix + "\\"):
        sub = clean[len(user_desktop_prefix) + 1 :].lstrip("\\/")
        return (desktop_dir / sub).resolve()

    # 5. General path expansion
    expanded = os.path.expandvars(os.path.expanduser(clean))
    p = Path(expanded).resolve()

    # 6. If resolved path doesn't exist, but contains a \Desktop\ element
    if not p.exists():
        parts = list(p.parts)
        for i, part in enumerate(parts):
            if part.lower() == "desktop":
                sub_parts = parts[i + 1 :]
                return desktop_dir.joinpath(*sub_parts).resolve()

    return p


class FilesystemOperations:
    @staticmethod
    def list_dir(path: str) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not p.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        entries = []
        for item in p.iterdir():
            try:
                stat = item.stat()
                entries.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size_bytes": stat.st_size if not item.is_dir() else None,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except (PermissionError, FileNotFoundError):
                continue

        # Sort folders first, then files by name
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return {
            "path": str(p),
            "count": len(entries),
            "truncated": len(entries) > 50,
            "entries": entries[:50],  # Bound result set to prevent token explosion
        }

    @staticmethod
    def file_metadata(path: str) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            raise FileNotFoundError(f"File or directory not found: {path}")

        stat = p.stat()
        return {
            "path": str(p),
            "name": p.name,
            "is_dir": p.is_dir(),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2) if not p.is_dir() else None,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "extension": p.suffix if not p.is_dir() else None,
        }

    @staticmethod
    def search_files(
        path: str,
        pattern: str = "*",
        recursive: bool = True,
        max_results: int = 50,
    ) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            raise FileNotFoundError(f"Search root path not found: {path}")

        matches = []
        pattern_lower = pattern.lower()

        # If pattern is a specific filename or wildcards
        search_pattern = f"**/{pattern}" if recursive else pattern
        try:
            for item in p.glob(search_pattern):
                if len(matches) >= max_results:
                    break
                try:
                    stat = item.stat()
                    matches.append({
                        "name": item.name,
                        "path": str(item.resolve()),
                        "is_dir": item.is_dir(),
                        "size_bytes": stat.st_size if not item.is_dir() else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                except (PermissionError, FileNotFoundError):
                    continue
        except Exception:
            # Fallback for complex searches
            for root, dirs, files in os.walk(p):
                if len(matches) >= max_results:
                    break
                for f in files:
                    if pattern_lower in f.lower() or glob.fnmatch.fnmatch(f.lower(), pattern_lower):
                        full = Path(root) / f
                        matches.append({"name": f, "path": str(full.resolve()), "is_dir": False})
                        if len(matches) >= max_results:
                            break

        # If exact search returned no matches and pattern is specific, perform typo-tolerant fuzzy matching
        if not matches and pattern.strip("*"):
            clean_pat = re.sub(r"[^a-zA-Z0-9]", " ", pattern).lower()
            pat_words = [w for w in clean_pat.split() if len(w) > 2 and w not in ("pdf", "png", "jpg", "txt", "docx")]
            if pat_words:
                target_ext = Path(pattern).suffix.lower() if Path(pattern).suffix else None
                candidate_items = p.rglob("*") if recursive else p.iterdir()
                try:
                    for item in candidate_items:
                        if len(matches) >= max_results:
                            break
                        if target_ext and item.suffix.lower() != target_ext:
                            continue
                        clean_fn = re.sub(r"[^a-zA-Z0-9]", " ", item.name).lower()
                        fn_words = [w for w in clean_fn.split() if len(w) > 2]
                        word_match = True
                        for pw in pat_words:
                            close = difflib.get_close_matches(pw, fn_words, cutoff=0.7)
                            if not close and not any(pw[:4] in fw for fw in fn_words if len(fw) >= 4):
                                word_match = False
                                break
                        if word_match:
                            try:
                                stat = item.stat()
                                matches.append({
                                    "name": item.name,
                                    "path": str(item.resolve()),
                                    "is_dir": item.is_dir(),
                                    "size_bytes": stat.st_size if not item.is_dir() else None,
                                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                })
                            except (PermissionError, FileNotFoundError):
                                continue
                except Exception:
                    pass

                # Sort fuzzy matches by similarity to search pattern
                clean_target = pattern.replace("*", "").lower()
                matches.sort(
                    key=lambda m: difflib.SequenceMatcher(None, clean_target, m["name"].lower()).ratio(),
                    reverse=True,
                )

        return {
            "search_root": str(p),
            "pattern": pattern,
            "total_found": len(matches),
            "results": matches,
        }

    @staticmethod
    def make_dir(path: str) -> Dict[str, Any]:
        p = resolve_system_path(path)
        p.mkdir(parents=True, exist_ok=True)
        return {"created": True, "path": str(p)}

    @staticmethod
    def write_text_file(path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
        """Create a UTF-8 text file without silently replacing an existing file."""
        p = resolve_system_path(path)
        existed_before_write = p.exists()
        if existed_before_write and not overwrite:
            raise FileExistsError(f"File already exists and overwrite was not approved: {path}")
        if p.exists() and p.is_dir():
            raise IsADirectoryError(f"Cannot write text to a directory: {path}")

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {
            "written": True,
            "path": str(p),
            "bytes_written": len(content.encode("utf-8")),
            "overwritten": existed_before_write,
        }

    @staticmethod
    def copy_file(src: str, dst: str) -> Dict[str, Any]:
        source = resolve_system_path(src)
        destination = resolve_system_path(dst)
        if not source.exists():
            raise FileNotFoundError(f"Source does not exist: {src}")

        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            if destination.is_dir():
                destination = destination / source.name
            shutil.copy2(source, destination)

        return {"copied": True, "source": str(source), "destination": str(destination)}

    @staticmethod
    def move_file(src: str, dst: str) -> Dict[str, Any]:
        source = resolve_system_path(src)
        destination = resolve_system_path(dst)
        if not source.exists():
            raise FileNotFoundError(f"Source does not exist: {src}")

        shutil.move(str(source), str(destination))
        return {"moved": True, "source": str(source), "destination": str(destination)}

    @staticmethod
    def rename_file(path: str, new_name: str) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        new_path = p.parent / new_name
        p.rename(new_path)
        return {"renamed": True, "old_path": str(p), "new_path": str(new_path)}

    @staticmethod
    def delete_file(path: str) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            return {"deleted": True, "path": str(p), "existed": False}

        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()

        return {"deleted": True, "path": str(p), "existed": True}

    @staticmethod
    def open_file(path: str) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            raise FileNotFoundError(f"Cannot open non-existent path: {path}")

        # Use native Windows os.startfile
        os.startfile(str(p))
        return {"opened": True, "path": str(p)}

    @staticmethod
    def read_text_file(path: str, max_chars: int = 5000) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if p.is_dir():
            raise IsADirectoryError(f"Cannot read text from a directory: {path}")

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)

        return {
            "path": str(p),
            "content": content,
            "truncated": len(content) >= max_chars,
        }

    @staticmethod
    def list_downloads(
        limit: int = 10,
        drive: Optional[str] = None,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        if path:
            downloads_dir = resolve_system_path(path)
        elif drive:
            drive_clean = drive.rstrip(":\\/ ").upper() + ":\\"
            downloads_dir = resolve_system_path(f"{drive_clean}Downloads")
            if not downloads_dir.exists():
                downloads_dir = resolve_system_path(drive_clean)
        else:
            downloads_dir = get_special_folder("downloads")

        if not downloads_dir.exists():
            return {"downloads_path": str(downloads_dir), "count": 0, "entries": []}

        items = []
        for p in downloads_dir.iterdir():
            try:
                stat = p.stat()
                items.append({
                    "name": p.name,
                    "path": str(p.resolve()),
                    "is_dir": p.is_dir(),
                    "size_bytes": stat.st_size if not p.is_dir() else None,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2) if not p.is_dir() else None,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "mtime_raw": stat.st_mtime,
                })
            except (PermissionError, FileNotFoundError):
                continue

        # Sort by most recent modification time descending
        items.sort(key=lambda x: x["mtime_raw"], reverse=True)
        limited = items[:limit]

        # Clean raw mtime
        for item in limited:
            del item["mtime_raw"]

        return {
            "downloads_path": str(downloads_dir),
            "count": len(limited),
            "entries": limited,
        }
