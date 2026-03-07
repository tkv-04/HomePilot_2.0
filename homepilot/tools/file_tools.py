"""
File operation tools for HomePilot agent.

Provides sandboxed file read/write/list operations.
All paths are validated to prevent directory traversal attacks.
"""

from __future__ import annotations

import os
from pathlib import Path

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.tools.file")

# Maximum file size to read (10 MB)
_MAX_READ_SIZE = 10 * 1024 * 1024

# Dangerous path components
_BLOCKED_PATHS = {
    "/etc/shadow", "/etc/passwd", "/etc/sudoers",
    "C:\\Windows\\System32", "C:\\Windows\\SysWOW64",
}


def register_tools(router: "ToolRouter") -> None:
    """Register all file tools with the tool router."""
    from homepilot.core.tool_router import ToolRouter

    router.register(
        name="read_file",
        func=read_file,
        description="Read the contents of a text file",
        parameter_descriptions={"path": "Absolute or relative path to the file"},
    )
    router.register(
        name="write_file",
        func=write_file,
        description="Write content to a file (creates or overwrites)",
        parameter_descriptions={
            "path": "Path to the file to write",
            "content": "Text content to write",
        },
        permission_key="allow_file_write",
    )
    router.register(
        name="list_directory",
        func=list_directory,
        description="List files and folders in a directory",
        parameter_descriptions={"path": "Path to the directory (default: current directory)"},
    )


def _validate_path(path_str: str) -> tuple[bool, str, Path | None]:
    """
    Validate a file path for safety.

    Returns:
        Tuple of (is_safe, reason, resolved_path).
    """
    if not path_str:
        return False, "No path provided.", None

    try:
        p = Path(path_str).resolve()
    except Exception as e:
        return False, f"Invalid path: {e}", None

    # Block sensitive system paths
    p_str = str(p)
    for blocked in _BLOCKED_PATHS:
        if p_str.startswith(blocked):
            return False, f"Access to '{blocked}' is not allowed.", None

    return True, "OK", p


def read_file(path: str = "") -> str:
    """Read the contents of a text file."""
    ok, reason, resolved = _validate_path(path)
    if not ok:
        return f"Error: {reason}"

    if not resolved.exists():
        return f"Error: File not found: {path}"
    if not resolved.is_file():
        return f"Error: '{path}' is not a file."
    if resolved.stat().st_size > _MAX_READ_SIZE:
        return f"Error: File is too large (>{_MAX_READ_SIZE // (1024*1024)} MB)."

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
        line_count = content.count("\n") + 1
        # Truncate very long files for the agent
        if len(content) > 5000:
            content = content[:5000] + f"\n... (truncated, {line_count} total lines)"
        return f"File: {resolved.name} ({line_count} lines)\n\n{content}"
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(path: str = "", content: str = "") -> str:
    """Write content to a file."""
    ok, reason, resolved = _validate_path(path)
    if not ok:
        return f"Error: {reason}"

    try:
        # Create parent directories if needed
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} bytes to {resolved.name}."
    except Exception as e:
        return f"Error writing file: {e}"


def list_directory(path: str = ".") -> str:
    """List files and folders in a directory."""
    ok, reason, resolved = _validate_path(path)
    if not ok:
        return f"Error: {reason}"

    if not resolved.exists():
        return f"Error: Directory not found: {path}"
    if not resolved.is_dir():
        return f"Error: '{path}' is not a directory."

    try:
        entries = sorted(resolved.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        lines = [f"Contents of {resolved}:"]
        for entry in entries[:50]:  # Limit to 50 entries
            if entry.is_dir():
                lines.append(f"  📁 {entry.name}/")
            else:
                size = entry.stat().st_size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                lines.append(f"  📄 {entry.name} ({size_str})")

        total = len(list(resolved.iterdir()))
        if total > 50:
            lines.append(f"  ... and {total - 50} more entries")

        return "\n".join(lines)
    except PermissionError:
        return f"Error: Permission denied for directory: {path}"
    except Exception as e:
        return f"Error listing directory: {e}"
