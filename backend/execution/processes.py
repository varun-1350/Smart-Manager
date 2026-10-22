import os
import subprocess
import shutil
from typing import Dict, Any, List, Optional
import psutil


class ProcessOperations:
    @staticmethod
    def list_processes(filter_name: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        results = []
        filter_lower = filter_name.lower() if filter_name else None

        for proc in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info"]):
            try:
                info = proc.info
                name = info.get("name") or ""
                if filter_lower and filter_lower not in name.lower():
                    continue

                mem = info.get("memory_info")
                mem_mb = round(mem.rss / (1024 * 1024), 1) if mem else 0.0

                results.append({
                    "pid": info["pid"],
                    "name": name,
                    "user": info.get("username"),
                    "memory_mb": mem_mb,
                })
                if len(results) >= limit:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        results.sort(key=lambda x: x["memory_mb"], reverse=True)
        return {"count": len(results), "processes": results}

    @staticmethod
    def process_info(pid: int) -> Dict[str, Any]:
        try:
            p = psutil.Process(pid)
            with p.oneshot():
                return {
                    "pid": p.pid,
                    "name": p.name(),
                    "exe": p.exe(),
                    "status": p.status(),
                    "cpu_percent": p.cpu_percent(),
                    "memory_mb": round(p.memory_info().rss / (1024 * 1024), 2),
                    "create_time": p.create_time(),
                }
        except psutil.NoSuchProcess:
            raise ProcessLookupError(f"No active process found with PID {pid}")
        except psutil.AccessDenied:
            raise PermissionError(f"Access denied to process PID {pid}")

    @staticmethod
    def launch_process(target: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Launches an application or executable. Handles both direct executables
        and registered Windows applications / protocol schemes.
        """
        cmd_args = args or []

        # If it's a known executable or command
        resolved_exe = shutil.which(target)
        if resolved_exe:
            proc = subprocess.Popen([resolved_exe] + cmd_args, shell=False)
            return {"launched": True, "target": target, "pid": proc.pid}

        # Otherwise launch via Windows shell start (e.g. for Store apps, Asphalt Legends, etc.)
        try:
            # os.startfile handles store apps, shortcuts, and registered protocols cleanly
            os.startfile(target)
            return {"launched": True, "target": target, "method": "startfile"}
        except Exception:
            # Fallback to powershell Start-Process
            ps_cmd = f"Start-Process '{target}'"
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", ps_cmd], shell=False)
            return {"launched": True, "target": target, "method": "powershell_start"}

    @staticmethod
    def terminate_process(pid: int) -> Dict[str, Any]:
        try:
            p = psutil.Process(pid)
            name = p.name()
            p.terminate()
            p.wait(timeout=3)
            return {"terminated": True, "pid": pid, "name": name}
        except psutil.TimeoutExpired:
            p.kill()
            return {"terminated": True, "pid": pid, "force_killed": True}
        except psutil.NoSuchProcess:
            return {"terminated": True, "pid": pid, "already_exited": True}

    @staticmethod
    def storage_info() -> Dict[str, Any]:
        """
        Inspects all mounted physical partitions and returns total, used, free space and usage percentage.
        """
        partitions = psutil.disk_partitions(all=False)
        drives = []

        for part in partitions:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                drives.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent_used": usage.percent,
                })
            except (PermissionError, FileNotFoundError):
                continue

        return {"drives": drives}
