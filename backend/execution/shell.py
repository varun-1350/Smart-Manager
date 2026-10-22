import subprocess
from typing import Dict, Any


class ShellOperations:
    @staticmethod
    def run_command(command: str, timeout_seconds: int = 15) -> Dict[str, Any]:
        """
        Executes a controlled PowerShell command.
        """
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            return {
                "command": command,
                "exit_code": res.returncode,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
                "success": res.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {
                "command": command,
                "exit_code": -1,
                "error": f"Command timed out after {timeout_seconds} seconds.",
                "success": False,
            }
        except Exception as e:
            return {
                "command": command,
                "exit_code": -1,
                "error": str(e),
                "success": False,
            }
