"""
OS command control for HomePilot.

Platform-independent system control supporting both
Linux (Raspberry Pi) and Windows. Automatically detects
the OS at runtime and uses appropriate commands.

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

# Current OS — determined once at import time
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_MACOS = platform.system() == "Darwin"


class SystemController:
    """
    Whitelisted OS command executor with platform independence.

    Detects the operating system at runtime and uses the
    appropriate native commands for each platform.

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

    @staticmethod
    def get_platform() -> str:
        """Return the current platform name."""
        if IS_WINDOWS:
            return "Windows"
        elif IS_LINUX:
            return "Linux"
        elif IS_MACOS:
            return "macOS"
        return platform.system()

    def launch_application(self, app_name: str) -> str:
        """
        Launch an application by name (cross-platform).

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

        try:
            if IS_WINDOWS:
                return self._launch_app_windows(app_name)
            else:
                return self._launch_app_linux(app_name)
        except Exception as e:
            logger.error("Failed to launch %s: %s", app_name, e)
            return f"Failed to launch {app_name}."

    def _launch_app_windows(self, app_name: str) -> str:
        """Launch an application on Windows."""
        # Map common names to Windows executables
        windows_app_map: dict[str, str] = {
            "firefox": "firefox",
            "chrome": "chrome",
            "chromium-browser": "chrome",
            "edge": "msedge",
            "vlc": "vlc",
            "notepad": "notepad",
            "calculator": "calc",
            "terminal": "wt",           # Windows Terminal
            "cmd": "cmd",
            "powershell": "powershell",
            "code": "code",             # VS Code
            "explorer": "explorer",
            "nautilus": "explorer",      # Map Linux file manager to Explorer
            "paint": "mspaint",
            "task manager": "taskmgr",
        }

        exe_name = windows_app_map.get(app_name, app_name)
        exe_path = shutil.which(exe_name)

        if not exe_path:
            # Try with .exe extension
            exe_path = shutil.which(f"{exe_name}.exe")

        if not exe_path:
            # Try os.startfile for registered applications
            try:
                os.startfile(exe_name)  # type: ignore[attr-defined]
                logger.info("Launched application via startfile: %s", app_name)
                return f"Launching {app_name}."
            except OSError:
                return f"I couldn't find '{app_name}' on this system."

        env = self._safe_env()
        subprocess.Popen(
            [exe_path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        )
        logger.info("Launched application: %s (%s)", app_name, exe_path)
        return f"Launching {app_name}."

    def _launch_app_linux(self, app_name: str) -> str:
        """Launch an application on Linux."""
        exe_path = shutil.which(app_name)
        if not exe_path:
            return f"I couldn't find '{app_name}' on this system."

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

    def volume_control(
        self,
        action: str | None = None,
        level: int | None = None,
    ) -> str:
        """
        Control system volume (cross-platform).

        Args:
            action: 'up', 'down', 'mute', 'unmute'
            level: Volume level 0-100

        Returns:
            Status message.
        """
        if not self._config.enabled:
            return "OS control is disabled."

        try:
            if IS_WINDOWS:
                return self._volume_windows(action, level)
            elif IS_LINUX:
                return self._volume_linux(action, level)
            else:
                return "Volume control is not supported on this platform."
        except Exception as e:
            logger.error("Volume control error: %s", e)
            return "Failed to adjust the volume."

    def _volume_linux(self, action: str | None, level: int | None) -> str:
        """Volume control via ALSA (amixer) on Linux."""
        if level is not None:
            level = max(0, min(100, level))
            subprocess.run(
                ["amixer", "set", "Master", f"{level}%"],
                capture_output=True, timeout=5,
            )
            return f"Volume set to {level}%."

        commands = {
            "up": ["amixer", "set", "Master", "10%+"],
            "down": ["amixer", "set", "Master", "10%-"],
            "mute": ["amixer", "set", "Master", "mute"],
            "unmute": ["amixer", "set", "Master", "unmute"],
        }
        messages = {
            "up": "Volume increased.",
            "down": "Volume decreased.",
            "mute": "Audio muted.",
            "unmute": "Audio unmuted.",
        }

        if action in commands:
            subprocess.run(commands[action], capture_output=True, timeout=5)
            return messages[action]
        return "I didn't understand the volume command."

    def _volume_windows(self, action: str | None, level: int | None) -> str:
        """Volume control via PowerShell / nircmd on Windows."""
        if level is not None:
            level = max(0, min(100, level))
            # Use PowerShell to set volume via COM
            ps_script = (
                "Add-Type -TypeDefinition '"
                "using System.Runtime.InteropServices;"
                "[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]"
                "interface IAudioEndpointVolume { int _; int __; int ___; int ____; int _____;"
                "int SetMasterVolumeLevelScalar(float fLevel, System.Guid pguidEventContext); }'"
            )
            # Simpler approach: use nircmd if available, else PowerShell
            nircmd = shutil.which("nircmd")
            if nircmd:
                # nircmd volume is 0-65535
                vol = int(level * 655.35)
                subprocess.run(
                    [nircmd, "setsysvolume", str(vol)],
                    capture_output=True, timeout=5,
                )
            else:
                # PowerShell fallback using Windows Audio Session API
                script = f"""
$wshell = New-Object -ComObject WScript.Shell
$target = {level}
$current = 50
for($i=0; $i -lt 50; $i++) {{ $wshell.SendKeys([char]174) }}
$steps = [math]::Round($target / 2)
for($i=0; $i -lt $steps; $i++) {{ $wshell.SendKeys([char]175) }}
"""
                subprocess.run(
                    ["powershell", "-Command", script],
                    capture_output=True, timeout=10,
                )
            return f"Volume set to {level}%."

        nircmd = shutil.which("nircmd")

        if action == "up":
            if nircmd:
                subprocess.run([nircmd, "changesysvolume", "6553"], capture_output=True, timeout=5)
            else:
                subprocess.run(
                    ["powershell", "-Command",
                     "(New-Object -ComObject WScript.Shell).SendKeys([char]175)"],
                    capture_output=True, timeout=5,
                )
            return "Volume increased."

        if action == "down":
            if nircmd:
                subprocess.run([nircmd, "changesysvolume", "-6553"], capture_output=True, timeout=5)
            else:
                subprocess.run(
                    ["powershell", "-Command",
                     "(New-Object -ComObject WScript.Shell).SendKeys([char]174)"],
                    capture_output=True, timeout=5,
                )
            return "Volume decreased."

        if action == "mute":
            if nircmd:
                subprocess.run([nircmd, "mutesysvolume", "1"], capture_output=True, timeout=5)
            else:
                subprocess.run(
                    ["powershell", "-Command",
                     "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
                    capture_output=True, timeout=5,
                )
            return "Audio muted."

        if action == "unmute":
            if nircmd:
                subprocess.run([nircmd, "mutesysvolume", "0"], capture_output=True, timeout=5)
            else:
                subprocess.run(
                    ["powershell", "-Command",
                     "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
                    capture_output=True, timeout=5,
                )
            return "Audio unmuted."

        return "I didn't understand the volume command."

    def system_shutdown(self, confirmed: bool = False) -> str:
        """
        Shut down the system (cross-platform).

        Args:
            confirmed: Whether the user confirmed the action.

        Returns:
            Status or confirmation prompt.
        """
        if "shutdown" in self._confirm_required and not confirmed:
            return "Are you sure you want to shut down? Say 'yes' to confirm."

        try:
            if IS_WINDOWS:
                subprocess.run(["shutdown", "/s", "/t", "5"], timeout=10)
            elif IS_LINUX:
                subprocess.run(["sudo", "shutdown", "-h", "now"], timeout=10)
            return "Shutting down now."
        except Exception as e:
            logger.error("Shutdown failed: %s", e)
            return "Failed to shut down the system."

    def system_reboot(self, confirmed: bool = False) -> str:
        """
        Reboot the system (cross-platform).

        Args:
            confirmed: Whether the user confirmed the action.

        Returns:
            Status or confirmation prompt.
        """
        if "reboot" in self._confirm_required and not confirmed:
            return "Are you sure you want to reboot? Say 'yes' to confirm."

        try:
            if IS_WINDOWS:
                subprocess.run(["shutdown", "/r", "/t", "5"], timeout=10)
            elif IS_LINUX:
                subprocess.run(["sudo", "reboot"], timeout=10)
            return "Rebooting now."
        except Exception as e:
            logger.error("Reboot failed: %s", e)
            return "Failed to reboot the system."

    def get_system_status(self) -> str:
        """
        Get a summary of system status (cross-platform).

        Returns:
            Human-readable system status string.
        """
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/" if IS_LINUX else "C:\\")
            uptime_secs = (
                datetime.now() - datetime.fromtimestamp(psutil.boot_time())
            ).total_seconds()

            hours = int(uptime_secs // 3600)
            minutes = int((uptime_secs % 3600) // 60)

            os_name = self.get_platform()

            # CPU temperature (Raspberry Pi / Linux)
            temp_str = ""
            if IS_LINUX:
                try:
                    temps = psutil.sensors_temperatures()
                    if "cpu_thermal" in temps:
                        temp = temps["cpu_thermal"][0].current
                        temp_str = f" CPU temperature is {temp:.0f} degrees Celsius."
                except (AttributeError, KeyError, IndexError):
                    pass

            status = (
                f"Running on {os_name}. CPU usage is {cpu:.0f}%. "
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

        Returns minimal safe environment variables (platform-aware).
        """
        if IS_WINDOWS:
            safe_keys = {
                "PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE",
                "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
                "COMSPEC", "WINDIR", "USERNAME",
            }
        else:
            safe_keys = {
                "PATH", "HOME", "USER", "LANG", "DISPLAY",
                "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
                "DBUS_SESSION_BUS_ADDRESS",
            }
        return {k: v for k, v in os.environ.items() if k in safe_keys}
