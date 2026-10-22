import os
import shutil
import glob
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional


class FilesystemOperations:
    @staticmethod
    def list_dir(path: str) -> Dict[str, Any]:
        p = Path(path).resolve()
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
        p = Path(path).resolve()
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
        p = Path(path).resolve()
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

        return {
            "search_root": str(p),
            "pattern": pattern,
            "total_found": len(matches),
            "results": matches,
        }

    @staticmethod
    def make_dir(path: str) -> Dict[str, Any]:
        p = Path(path).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return {"created": True, "path": str(p)}

    @staticmethod
    def write_text_file(path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
        """Create a UTF-8 text file without silently replacing an existing file."""
        p = Path(path).resolve()
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
        source = Path(src).resolve()
        destination = Path(dst).resolve()
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
        source = Path(src).resolve()
        destination = Path(dst).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Source does not exist: {src}")

        shutil.move(str(source), str(destination))
        return {"moved": True, "source": str(source), "destination": str(destination)}

    @staticmethod
    def rename_file(path: str, new_name: str) -> Dict[str, Any]:
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        new_path = p.parent / new_name
        p.rename(new_path)
        return {"renamed": True, "old_path": str(p), "new_path": str(new_path)}

    @staticmethod
    def delete_file(path: str) -> Dict[str, Any]:
        p = Path(path).resolve()
        if not p.exists():
            return {"deleted": True, "path": str(p), "existed": False}

        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()

        return {"deleted": True, "path": str(p), "existed": True}

    @staticmethod
    def open_file(path: str) -> Dict[str, Any]:
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Cannot open non-existent path: {path}")

        # Use native Windows os.startfile
        os.startfile(str(p))
        return {"opened": True, "path": str(p)}

    @staticmethod
    def read_text_file(path: str, max_chars: int = 5000) -> Dict[str, Any]:
        p = Path(path).resolve()
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
    def list_downloads(limit: int = 10) -> Dict[str, Any]:
        user_home = Path.home()
        downloads_dir = user_home / "Downloads"
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
