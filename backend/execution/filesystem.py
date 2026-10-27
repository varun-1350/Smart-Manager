import os
import shutil
import glob
import re
import difflib
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from config import settings

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
    MAX_RESULTS = 200
    MAX_TEXT_READ_CHARS = 1_000_000
    MAX_SEARCH_ENTRIES = 20_000
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
        max_results = max(1, min(int(max_results), FilesystemOperations.MAX_RESULTS))
        if not p.exists():
            raise FileNotFoundError(f"Search root path not found: {path}")

        matches = []
        scanned_entries = 0
        search_truncated = False
        pattern_lower = pattern.lower()

        # If pattern is a specific filename or wildcards
        search_pattern = f"**/{pattern}" if recursive else pattern
        try:
            for item in p.glob(search_pattern):
                scanned_entries += 1
                if scanned_entries > FilesystemOperations.MAX_SEARCH_ENTRIES:
                    search_truncated = True
                    break
                if len(matches) >= max_results:
                    search_truncated = True
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
                    search_truncated = True
                    break
                for f in files:
                    scanned_entries += 1
                    if scanned_entries > FilesystemOperations.MAX_SEARCH_ENTRIES:
                        search_truncated = True
                        break
                    if pattern_lower in f.lower() or glob.fnmatch.fnmatch(f.lower(), pattern_lower):
                        full = Path(root) / f
                        matches.append({"name": f, "path": str(full.resolve()), "is_dir": False})
                        if len(matches) >= max_results:
                            break
                if search_truncated:
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
                        scanned_entries += 1
                        if scanned_entries > FilesystemOperations.MAX_SEARCH_ENTRIES:
                            search_truncated = True
                            break
                        if len(matches) >= max_results:
                            search_truncated = True
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
            # Avoid a pathological full-drive traversal when a model supplies
            # a broad or misspelled pattern.
            "truncated": search_truncated,
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
            if destination == source or source in destination.parents:
                raise ValueError("Cannot copy a directory into itself or one of its children.")
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            if destination.is_dir():
                destination = destination / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        return {"copied": True, "source": str(source), "destination": str(destination)}

    @staticmethod
    def move_file(src: str, dst: str) -> Dict[str, Any]:
        source = resolve_system_path(src)
        destination = resolve_system_path(dst)
        if not source.exists():
            raise FileNotFoundError(f"Source does not exist: {src}")

        if source.is_dir() and (destination == source or source in destination.parents):
            raise ValueError("Cannot move a directory into itself or one of its children.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return {"moved": True, "source": str(source), "destination": str(destination)}

    @staticmethod
    def rename_file(path: str, new_name: str) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        if not new_name or Path(new_name).name != new_name or new_name in {".", ".."}:
            raise ValueError("New name must not contain a path separator.")
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

        max_chars = max(1, min(int(max_chars), FilesystemOperations.MAX_TEXT_READ_CHARS))
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

    @staticmethod
    def get_file_category(name: str, is_dir: bool = False) -> str:
        if is_dir:
            return "folder"
        ext = Path(name).suffix.lower().lstrip(".")
        categories = {
            "documents": {"pdf", "doc", "docx", "odt", "rtf", "tex"},
            "spreadsheets": {"xls", "xlsx", "csv", "ods", "tsv"},
            "presentations": {"ppt", "pptx", "odp"},
            "images": {"png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "tiff", "ico", "heic"},
            "videos": {"mp4", "mkv", "mov", "avi", "wmv", "flv", "webm", "m4v"},
            "audio": {"mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"},
            "archives": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"},
            "code": {"py", "js", "jsx", "ts", "tsx", "html", "css", "json", "xml", "rs", "c", "cpp", "h", "go", "java", "php", "rb", "sql", "sh", "bat", "ps1"},
            "text": {"txt", "md", "log", "rst", "ini", "conf", "yaml", "yml"},
            "executables": {"exe", "msi", "dll"},
        }
        for cat, exts in categories.items():
            if ext in exts:
                return cat
        return "other"

    @staticmethod
    def format_size(bytes_val: Optional[int]) -> str:
        if bytes_val is None:
            return "--"
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{round(bytes_val / 1024, 1)} KB"
        elif bytes_val < 1024 * 1024 * 1024:
            return f"{round(bytes_val / (1024 * 1024), 1)} MB"
        else:
            return f"{round(bytes_val / (1024 * 1024 * 1024), 2)} GB"

    @staticmethod
    def get_breadcrumbs(p: Path) -> List[Dict[str, str]]:
        crumbs = []
        curr = p
        parts = []
        while curr and curr != curr.parent:
            name = curr.name or str(curr)
            parts.append({"name": name, "path": str(curr)})
            curr = curr.parent
        if curr:
            parts.append({"name": str(curr), "path": str(curr)})
        parts.reverse()
        return parts

    @staticmethod
    def browse_directory(
        path: Optional[str] = None,
        sort_by: str = "name",
        sort_order: str = "asc",
        show_hidden: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not p.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        entries = []
        try:
            for item in p.iterdir():
                is_hidden = item.name.startswith(".") or (
                    os.name == "nt"
                    and hasattr(item.stat(), "st_file_attributes")
                    and bool(item.stat().st_file_attributes & 2)
                )
                if not show_hidden and is_hidden:
                    continue
                try:
                    stat = item.stat()
                    is_dir = item.is_dir()
                    size = stat.st_size if not is_dir else None
                    entries.append({
                        "name": item.name,
                        "path": str(item.resolve()),
                        "is_dir": is_dir,
                        "size_bytes": size,
                        "size_formatted": FilesystemOperations.format_size(size),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "mtime_raw": stat.st_mtime,
                        "extension": item.suffix.lower().lstrip(".") if not is_dir else "",
                        "category": FilesystemOperations.get_file_category(item.name, is_dir),
                        "is_hidden": is_hidden,
                    })
                except (PermissionError, FileNotFoundError):
                    continue
        except PermissionError:
            raise PermissionError(f"Access denied to directory: {str(p)}")

        # Sorting logic: folders always grouped first
        reverse = sort_order.lower() == "desc"
        if sort_by == "size":
            entries.sort(key=lambda x: (not x["is_dir"], (x["size_bytes"] or 0) * (-1 if reverse else 1)))
        elif sort_by in ("date", "modified"):
            entries.sort(key=lambda x: (not x["is_dir"], x["mtime_raw"] * (-1 if reverse else 1)))
        elif sort_by in ("type", "category"):
            entries.sort(key=lambda x: (not x["is_dir"], x["category"].lower(), x["name"].lower()), reverse=reverse)
        else:
            entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()), reverse=reverse)

        total_count = len(entries)
        paged_entries = entries[offset : offset + limit]
        for e in paged_entries:
            e.pop("mtime_raw", None)

        parent_path = str(p.parent) if p.parent != p else None

        return {
            "current_path": str(p),
            "parent_path": parent_path,
            "breadcrumbs": FilesystemOperations.get_breadcrumbs(p),
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "entries": paged_entries,
        }

    @staticmethod
    def get_quick_locations() -> List[Dict[str, Any]]:
        locations = []
        specials = [
            ("Desktop", "desktop", "desktop"),
            ("Documents", "documents", "documents"),
            ("Downloads", "downloads", "downloads"),
            ("Pictures", "pictures", "pictures"),
            ("Music", "music", "music"),
            ("Videos", "videos", "videos"),
        ]
        for label, name, cat in specials:
            try:
                folder_path = get_special_folder(name)
                if folder_path.exists():
                    locations.append({
                        "id": name,
                        "label": label,
                        "path": str(folder_path),
                        "type": "folder",
                        "category": cat,
                    })
            except Exception:
                pass

        import psutil
        try:
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    locations.append({
                        "id": f"drive-{part.device.replace(':', '').replace('\\', '').lower()}",
                        "label": f"Local Disk ({part.device.rstrip('\\')})",
                        "path": str(Path(part.mountpoint).resolve()),
                        "type": "drive",
                        "total_gb": round(usage.total / (1024**3), 1),
                        "free_gb": round(usage.free / (1024**3), 1),
                        "percent_used": usage.percent,
                    })
                except Exception:
                    continue
        except Exception:
            pass

        return locations

    @staticmethod
    def get_trash_dir() -> Path:
        trash = settings.data_dir / "trash"
        trash.mkdir(parents=True, exist_ok=True)
        return trash

    @staticmethod
    def safe_trash(paths: List[str], batch_id: Optional[str] = None) -> Dict[str, Any]:
        from storage.history import OperationHistoryRepository
        from uuid import uuid4
        batch = batch_id or f"batch-{uuid4()}"
        trash_dir = FilesystemOperations.get_trash_dir()
        trashed = []
        for p_str in paths:
            source = resolve_system_path(p_str)
            if not source.exists():
                continue
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trash_target = trash_dir / f"{timestamp}_{source.name}"
            shutil.move(str(source), str(trash_target))
            OperationHistoryRepository.record_operation(
                batch_id=batch,
                operation_type="trash",
                source_path=str(source),
                destination_path=str(trash_target),
                extra_data={"original_name": source.name},
            )
            trashed.append({"source": str(source), "trash_path": str(trash_target)})
        return {"success": True, "batch_id": batch, "trashed_count": len(trashed), "trashed": trashed}

    @staticmethod
    def safe_move(src_paths: List[str], dest_folder: str, batch_id: Optional[str] = None) -> Dict[str, Any]:
        from storage.history import OperationHistoryRepository
        from uuid import uuid4
        batch = batch_id or f"batch-{uuid4()}"
        dest = resolve_system_path(dest_folder)
        dest.mkdir(parents=True, exist_ok=True)
        moved = []
        for p_str in src_paths:
            source = resolve_system_path(p_str)
            if not source.exists():
                continue
            target = dest / source.name
            if target.exists() and target != source:
                stem = source.stem
                suffix = source.suffix
                target = dest / f"{stem}_{datetime.now().strftime('%H%M%S')}{suffix}"
            shutil.move(str(source), str(target))
            OperationHistoryRepository.record_operation(
                batch_id=batch,
                operation_type="move",
                source_path=str(source),
                destination_path=str(target),
            )
            moved.append({"source": str(source), "destination": str(target)})
        return {"success": True, "batch_id": batch, "moved_count": len(moved), "moved": moved}

    @staticmethod
    def safe_copy(src_paths: List[str], dest_folder: str, batch_id: Optional[str] = None) -> Dict[str, Any]:
        from storage.history import OperationHistoryRepository
        from uuid import uuid4
        batch = batch_id or f"batch-{uuid4()}"
        dest = resolve_system_path(dest_folder)
        dest.mkdir(parents=True, exist_ok=True)
        copied = []
        for p_str in src_paths:
            source = resolve_system_path(p_str)
            if not source.exists():
                continue
            target = dest / source.name
            if target.exists():
                stem = source.stem
                suffix = source.suffix
                target = dest / f"{stem}_copy{suffix}"
            if source.is_dir():
                shutil.copytree(str(source), str(target), dirs_exist_ok=True)
            else:
                shutil.copy2(str(source), str(target))
            OperationHistoryRepository.record_operation(
                batch_id=batch,
                operation_type="copy",
                source_path=str(source),
                destination_path=str(target),
            )
            copied.append({"source": str(source), "destination": str(target)})
        return {"success": True, "batch_id": batch, "copied_count": len(copied), "copied": copied}

    @staticmethod
    def safe_rename(path: str, new_name: str, batch_id: Optional[str] = None) -> Dict[str, Any]:
        from storage.history import OperationHistoryRepository
        from uuid import uuid4
        batch = batch_id or f"batch-{uuid4()}"
        res = FilesystemOperations.rename_file(path, new_name)
        OperationHistoryRepository.record_operation(
            batch_id=batch,
            operation_type="rename",
            source_path=res["old_path"],
            destination_path=res["new_path"],
        )
        return {**res, "batch_id": batch}

    @staticmethod
    def undo_last_operation() -> Dict[str, Any]:
        from storage.history import OperationHistoryRepository
        last_batch = OperationHistoryRepository.get_last_undoable_batch()
        if not last_batch:
            return {"success": False, "message": "No operations available to undo."}

        batch_id = last_batch["batch_id"]
        operations = last_batch["operations"]
        undone_items = []
        errors = []

        for op in operations:
            op_type = op["operation_type"]
            src = op["source_path"]
            dst = op["destination_path"]

            try:
                if op_type == "move":
                    if dst and Path(dst).exists():
                        Path(src).parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(dst, src)
                        undone_items.append({"type": "move", "restored": src})
                elif op_type == "rename":
                    if dst and Path(dst).exists():
                        Path(dst).rename(src)
                        undone_items.append({"type": "rename", "restored": src})
                elif op_type == "trash":
                    if dst and Path(dst).exists():
                        Path(src).parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(dst, src)
                        undone_items.append({"type": "trash", "restored": src})
                elif op_type == "copy":
                    if dst and Path(dst).exists():
                        if Path(dst).is_dir():
                            shutil.rmtree(dst)
                        else:
                            Path(dst).unlink()
                        undone_items.append({"type": "copy", "removed": dst})
            except Exception as e:
                errors.append({"operation": op, "error": str(e)})

        OperationHistoryRepository.mark_batch_undone(batch_id)
        return {
            "success": len(errors) == 0,
            "batch_id": batch_id,
            "undone_count": len(undone_items),
            "undone_items": undone_items,
            "errors": errors,
        }

    @staticmethod
    def compute_sha256(path: Path, max_bytes: int = 50 * 1024 * 1024) -> Optional[str]:
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                chunk = f.read(65536)
                read_bytes = 0
                while chunk and read_bytes < max_bytes:
                    h.update(chunk)
                    read_bytes += len(chunk)
                    chunk = f.read(65536)
            return h.hexdigest()
        except Exception:
            return None

    @staticmethod
    def find_duplicates(folder_path: str, min_size_bytes: int = 1024, max_scan_files: int = 5000) -> Dict[str, Any]:
        p = resolve_system_path(folder_path)
        if not p.exists() or not p.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        by_size: Dict[int, List[Path]] = {}
        scanned = 0

        for item in p.rglob("*"):
            if scanned >= max_scan_files:
                break
            try:
                if item.is_file():
                    scanned += 1
                    sz = item.stat().st_size
                    if sz >= min_size_bytes:
                        by_size.setdefault(sz, []).append(item)
            except Exception:
                continue

        duplicate_clusters = []
        total_wasted_bytes = 0

        for sz, files in by_size.items():
            if len(files) < 2:
                continue
            by_hash: Dict[str, List[Path]] = {}
            for f in files:
                h = FilesystemOperations.compute_sha256(f)
                if h:
                    by_hash.setdefault(h, []).append(f)

            for h, cluster in by_hash.items():
                if len(cluster) > 1:
                    wasted = sz * (len(cluster) - 1)
                    total_wasted_bytes += wasted
                    duplicate_clusters.append({
                        "hash": h,
                        "size_bytes": sz,
                        "size_formatted": FilesystemOperations.format_size(sz),
                        "count": len(cluster),
                        "wasted_bytes": wasted,
                        "files": [
                            {
                                "name": f.name,
                                "path": str(f.resolve()),
                                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                            }
                            for f in cluster
                        ],
                    })

        duplicate_clusters.sort(key=lambda x: x["wasted_bytes"], reverse=True)
        return {
            "search_root": str(p),
            "scanned_files": scanned,
            "duplicate_groups_count": len(duplicate_clusters),
            "total_wasted_bytes": total_wasted_bytes,
            "total_wasted_formatted": FilesystemOperations.format_size(total_wasted_bytes),
            "duplicates": duplicate_clusters,
        }

    @staticmethod
    def analyze_storage(folder_path: str) -> Dict[str, Any]:
        p = resolve_system_path(folder_path)
        if not p.exists() or not p.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        large_files = []
        empty_folders = []
        temp_files = []
        scanned_files = 0
        temp_suffixes = {".tmp", ".bak", ".log", ".swp", ".cache", ".dmp"}
        temp_names = {"thumbs.db", ".ds_store", "desktop.ini"}

        for item in p.rglob("*"):
            scanned_files += 1
            if scanned_files > 8000:
                break
            try:
                if item.is_file():
                    stat = item.stat()
                    sz = stat.st_size
                    if sz > 50 * 1024 * 1024:
                        large_files.append({
                            "name": item.name,
                            "path": str(item.resolve()),
                            "size_bytes": sz,
                            "size_formatted": FilesystemOperations.format_size(sz),
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        })
                    if item.suffix.lower() in temp_suffixes or item.name.lower() in temp_names or item.name.startswith("~"):
                        temp_files.append({
                            "name": item.name,
                            "path": str(item.resolve()),
                            "size_bytes": sz,
                            "size_formatted": FilesystemOperations.format_size(sz),
                        })
                elif item.is_dir():
                    try:
                        next(item.iterdir())
                    except StopIteration:
                        empty_folders.append({
                            "name": item.name,
                            "path": str(item.resolve()),
                        })
                    except Exception:
                        pass
            except Exception:
                continue

        large_files.sort(key=lambda x: x["size_bytes"], reverse=True)
        return {
            "folder": str(p),
            "large_files": large_files[:30],
            "empty_folders": empty_folders[:50],
            "temp_files": temp_files[:50],
            "summary": {
                "large_file_count": len(large_files),
                "empty_folder_count": len(empty_folders),
                "temp_file_count": len(temp_files),
            },
        }

    @staticmethod
    def file_preview(path: str, max_chars: int = 15000) -> Dict[str, Any]:
        p = resolve_system_path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if p.is_dir():
            items = [item.name for item in p.iterdir()][:30]
            return {
                "type": "folder",
                "name": p.name,
                "path": str(p),
                "item_count": len(list(p.iterdir())),
                "sample_items": items,
            }

        stat = p.stat()
        ext = p.suffix.lower().lstrip(".")
        category = FilesystemOperations.get_file_category(p.name, False)

        preview_data = {
            "name": p.name,
            "path": str(p),
            "size_bytes": stat.st_size,
            "size_formatted": FilesystemOperations.format_size(stat.st_size),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "category": category,
            "extension": ext,
        }

        text_extensions = {"txt", "md", "json", "py", "js", "html", "css", "ts", "jsx", "tsx", "csv", "xml", "yaml", "yml", "ini", "log", "sql", "bat", "ps1", "sh"}
        if ext in text_extensions or category in ("text", "code", "spreadsheets"):
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(max_chars)
                    preview_data["content"] = content
                    preview_data["truncated"] = len(content) >= max_chars
                    preview_data["preview_type"] = "text"
                    return preview_data
            except Exception:
                pass

        preview_data["preview_type"] = "metadata"
        return preview_data

