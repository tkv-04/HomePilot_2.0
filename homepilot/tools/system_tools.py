"""
System tools for HomePilot agent.

Wraps SystemController functionality as agent-callable tools
that return structured string results.
"""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING

import psutil

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.os_control.system_commands import SystemController

logger = get_logger("homepilot.tools.system")

# Module-level reference set by register_tools()
_controller: SystemController | None = None


def register_tools(
    router: "ToolRouter",
    system_controller: SystemController | None = None,
) -> None:
    """
    Register all system tools with the tool router.

    Args:
        router: The ToolRouter instance.
        system_controller: The SystemController instance.
    """
    global _controller
    _controller = system_controller

    from homepilot.core.tool_router import ToolRouter

    router.register(
        name="cpu_usage",
        func=cpu_usage,
        description="Get current CPU usage percentage",
    )
    router.register(
        name="memory_usage",
        func=memory_usage,
        description="Get current RAM/memory usage",
    )
    router.register(
        name="system_status",
        func=system_status,
        description="Get full system status (CPU, RAM, disk, uptime)",
    )
    router.register(
        name="open_app",
        func=open_app,
        description="Open/launch an application by name",
        parameter_descriptions={"app_name": "Name of application to open (e.g. 'vscode', 'firefox', 'notepad')"},
    )
    router.register(
        name="shutdown_system",
        func=shutdown_system,
        description="Shut down the computer (requires confirmation)",
        permission_key="allow_system_restart",
    )
    router.register(
        name="restart_system",
        func=restart_system,
        description="Restart/reboot the computer (requires confirmation)",
        permission_key="allow_system_restart",
    )


def cpu_usage() -> str:
    """Get current CPU usage percentage."""
    percent = psutil.cpu_percent(interval=1)
    return f"CPU usage is currently at {percent}%."


def memory_usage() -> str:
    """Get current RAM/memory usage."""
    mem = psutil.virtual_memory()
    used_gb = mem.used / (1024 ** 3)
    total_gb = mem.total / (1024 ** 3)
    return (
        f"Memory usage: {mem.percent}% "
        f"({used_gb:.1f} GB used of {total_gb:.1f} GB total)."
    )


def system_status() -> str:
    """Get comprehensive system status."""
    if _controller:
        return _controller.get_system_status()

    # Fallback if no controller
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/") if platform.system() != "Windows" else psutil.disk_usage("C:\\")
    return (
        f"System: {platform.system()} {platform.release()}\n"
        f"CPU: {cpu}%\n"
        f"RAM: {mem.percent}% ({mem.used / (1024**3):.1f}/{mem.total / (1024**3):.1f} GB)\n"
        f"Disk: {disk.percent}% ({disk.used / (1024**3):.1f}/{disk.total / (1024**3):.1f} GB)"
    )


def open_app(app_name: str = "") -> str:
    """Open an application by name."""
    if not app_name:
        return "Error: Please specify an application name."
    if not _controller:
        return "Error: System controller not available."
    return _controller.launch_application(app_name)


def shutdown_system() -> str:
    """Shut down the system."""
    if not _controller:
        return "Error: System controller not available."
    return _controller.system_shutdown(confirmed=True)


def restart_system() -> str:
    """Restart the system."""
    if not _controller:
        return "Error: System controller not available."
    return _controller.system_reboot(confirmed=True)
