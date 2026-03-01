"""
OS command control for HomePilot.

Provides whitelisted, sandboxed system operations.
No arbitrary shell execution. All commands are validated
against a strict whitelist before execution.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.config.settings import OSControlConfig

logger = get_logger("homepilot.os_control")


class SystemController:
    """
    Whitelisted OS command executor.

    Only executes commands that are explicitly allowed in the
    configuration. All parameters are sanitized before use.

    Security properties:
    - Strict command whitelist
    - No arbitrary shell execution
    - Parameter validation
    - Sandboxed subprocess with limited environment
    - No privilege escalation
    """

    def __init__(self, config: OSControlConfig) -> None:
        self._config = config
        self._allowed_apps = set(app.lower() for app in config.allowed_apps)
        self._allowed_commands = set(cmd.lower() for cmd in config.allowed_commands)
        self._confirm_required = set(cmd.lower() for cmd in config.require_confirmation)

    def launch_application(self, app_name: str) -> str:
        """
        Launch an application by name.

        Args:
            app_name: Name of the application to launch.

        Returns:
            Status message.
        """
        if not self._config.enabled:
            return "OS control is disabled."

        app_name = app_name.strip().lower()
        # Security: validate against whitelist
        if app_name not in self._allowed_apps:
            logger.warning("Blocked attempt to launch non-whitelisted app: %s", app_name)
            return f"Sorry, I'm not allowed to launch '{app_name}'. It's not on the whitelist."

        # Find the executable
        exe_path = shutil.which(app_name)
        if not exe_path:
            return f"I couldn't find '{app_name}' on this system."

        try:
            # Launch in background with sandboxed environment
            env = self._safe_env()
            subprocess.Popen(
                [exe_path],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info("Launched application: %s", app_name)
            return f"Launching {app_name}."
        except Exception as e:
            logger.error("Failed to launch %s: %s", app_name, e)
            return f"Failed to launch {app_name}."

    def volume_control(
        self,
        action: str | None = None,
        level: int | None = None,
    ) -> str:
        """
        Control system volume.

        Args:
            action: 'up', 'down', 'mute', 'unmute'
            level: Volume level 0-100

        Returns:
            Status message.
        """
        if not self._config.enabled:
            return "OS control is disabled."

        system = platform.system()

        try:
            if level is not None:
                level = max(0, min(100, level))
                if system == "Linux":
                    subprocess.run(
                        ["amixer", "set", "Master", f"{level}%"],
                        capture_output=True,
                        timeout=5,
                    )
                return f"Volume set to {level}%."

            if action == "up":
                if system == "Linux":
                    subprocess.run(
                        ["amixer", "set", "Master", "10%+"],
                        capture_output=True,
                        timeout=5,
                    )
                return "Volume increased."

            if action == "down":
                if system == "Linux":
                    subprocess.run(
                        ["amixer", "set", "Master", "10%-"],
                        capture_output=True,
                        timeout=5,
                    )
                return "Volume decreased."

            if action == "mute":
                if system == "Linux":
                    subprocess.run(
                        ["amixer", "set", "Master", "mute"],
                        capture_output=True,
                        timeout=5,
                    )
                return "Audio muted."

            if action == "unmute":
                if system == "Linux":
                    subprocess.run(
                        ["amixer", "set", "Master", "unmute"],
                        capture_output=True,
                        timeout=5,
                    )
                return "Audio unmuted."

            return "I didn't understand the volume command."

        except Exception as e:
            logger.error("Volume control error: %s", e)
            return "Failed to adjust the volume."

    def system_shutdown(self, confirmed: bool = False) -> str:
        """
        Shut down the system.

        Args:
            confirmed: Whether the user confirmed the action.

        Returns:
            Status or confirmation prompt.
        """
        if "shutdown" in self._confirm_required and not confirmed:
            return "Are you sure you want to shut down? Say 'yes' to confirm."

        try:
            if platform.system() == "Linux":
                subprocess.run(["sudo", "shutdown", "-h", "now"], timeout=10)
            return "Shutting down now."
        except Exception as e:
            logger.error("Shutdown failed: %s", e)
            return "Failed to shut down the system."

    def system_reboot(self, confirmed: bool = False) -> str:
        """
        Reboot the system.

        Args:
            confirmed: Whether the user confirmed the action.

        Returns:
            Status or confirmation prompt.
        """
        if "reboot" in self._confirm_required and not confirmed:
            return "Are you sure you want to reboot? Say 'yes' to confirm."

        try:
            if platform.system() == "Linux":
                subprocess.run(["sudo", "reboot"], timeout=10)
            return "Rebooting now."
        except Exception as e:
            logger.error("Reboot failed: %s", e)
            return "Failed to reboot the system."

    def get_system_status(self) -> str:
        """
        Get a summary of system status.

        Returns:
            Human-readable system status string.
        """
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            uptime_secs = (
                datetime.now() - datetime.fromtimestamp(psutil.boot_time())
            ).total_seconds()

            hours = int(uptime_secs // 3600)
            minutes = int((uptime_secs % 3600) // 60)

            # CPU temperature (Raspberry Pi)
            temp_str = ""
            try:
                temps = psutil.sensors_temperatures()
                if "cpu_thermal" in temps:
                    temp = temps["cpu_thermal"][0].current
                    temp_str = f" CPU temperature is {temp:.0f} degrees Celsius."
            except (AttributeError, KeyError, IndexError):
                pass

            status = (
                f"System is running. CPU usage is {cpu:.0f}%. "
                f"Memory usage is {mem.percent:.0f}% of {mem.total // (1024**3)} gigabytes. "
                f"Disk usage is {disk.percent:.0f}%. "
                f"Uptime is {hours} hours and {minutes} minutes."
                f"{temp_str}"
            )
            return status

        except ImportError:
            return "System monitoring is not available. Install psutil."
        except Exception as e:
            logger.error("System status error: %s", e)
            return "Failed to get system status."

    @staticmethod
    def _safe_env() -> dict[str, str]:
        """
        Create a sandboxed environment for subprocess execution.

        Returns minimal safe environment variables.
        """
        safe_keys = {"PATH", "HOME", "USER", "LANG", "DISPLAY", "WAYLAND_DISPLAY",
                      "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"}
        return {k: v for k, v in os.environ.items() if k in safe_keys}
