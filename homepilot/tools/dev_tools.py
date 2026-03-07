"""
Developer tools for HomePilot agent.

Provides git operations and sandboxed script execution
for development workflows.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.tools.dev")

# Maximum script output length
_MAX_OUTPUT = 3000

# Timeout for subprocess commands (seconds)
_CMD_TIMEOUT = 30


def register_tools(router: "ToolRouter") -> None:
    """Register all developer tools with the tool router."""
    from homepilot.core.tool_router import ToolRouter

    router.register(
        name="git_pull",
        func=git_pull,
        description="Pull latest code from the current git repository",
        permission_key="allow_git_operations",
    )
    router.register(
        name="git_status",
        func=git_status,
        description="Show the current git repository status",
        permission_key="allow_git_operations",
    )
    router.register(
        name="run_python_script",
        func=run_python_script,
        description="Run a Python script file",
        parameter_descriptions={"path": "Path to the Python script (.py file)"},
        permission_key="allow_script_execution",
    )


def _run_command(cmd: list[str], cwd: str | None = None) -> str:
    """
    Run a subprocess command safely.

    Args:
        cmd: Command and arguments.
        cwd: Working directory.

    Returns:
        Combined stdout + stderr output.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT,
            cwd=cwd,
            env=_safe_env(),
        )
        output = result.stdout + result.stderr
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + "\n... (output truncated)"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {_CMD_TIMEOUT} seconds."
    except FileNotFoundError:
        return f"Error: Command not found: {cmd[0]}"
    except Exception as e:
        return f"Error running command: {e}"


def _safe_env() -> dict[str, str]:
    """Create a minimal safe environment for subprocess execution."""
    env: dict[str, str] = {}
    safe_keys = ["PATH", "HOME", "USER", "LANG", "TERM", "SystemRoot",
                 "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA",
                 "LOCALAPPDATA", "TEMP", "TMP"]
    for key in safe_keys:
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def git_pull() -> str:
    """Pull latest code from the current git repository."""
    return _run_command(["git", "pull"])


def git_status() -> str:
    """Show the current git repository status."""
    return _run_command(["git", "status", "--short", "--branch"])


def run_python_script(path: str = "") -> str:
    """Run a Python script file."""
    if not path:
        return "Error: Please provide a path to a Python script."

    script_path = Path(path).resolve()
    if not script_path.exists():
        return f"Error: Script not found: {path}"
    if not script_path.suffix == ".py":
        return "Error: Only .py files can be executed."
    if script_path.stat().st_size > 1024 * 1024:  # 1 MB max
        return "Error: Script file is too large."

    # Determine Python executable
    python = "python3" if platform.system() != "Windows" else "python"

    return _run_command(
        [python, str(script_path)],
        cwd=str(script_path.parent),
    )
