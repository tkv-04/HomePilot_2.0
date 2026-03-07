"""
Permission manager for HomePilot agent tools.

Loads permissions from config/permissions.json and provides
a simple allow/deny API used by the ToolRouter before
executing any tool.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.permissions")

# Default permissions applied when no permissions.json exists
_DEFAULTS: dict[str, bool] = {
    "allow_system_restart": True,
    "allow_file_delete": False,
    "allow_file_write": True,
    "allow_network_scan": False,
    "allow_git_operations": True,
    "allow_script_execution": True,
    "allow_ha_control": True,
}


class PermissionManager:
    """
    Tool-level permission gate.

    Reads config/permissions.json once at startup and exposes
    ``is_allowed(key)`` for the ToolRouter to call before
    executing any registered tool.
    """

    def __init__(self, permissions_path: str | Path | None = None) -> None:
        self._permissions: dict[str, bool] = dict(_DEFAULTS)

        if permissions_path:
            path = Path(permissions_path)
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data: dict[str, Any] = json.load(f)
                    self._permissions.update(
                        {k: bool(v) for k, v in data.items()}
                    )
                    logger.info(
                        "Loaded %d permission(s) from %s",
                        len(data), path,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to load permissions.json: %s — using defaults",
                        e,
                    )
            else:
                logger.info(
                    "No permissions.json found at %s — using defaults", path
                )

    def is_allowed(self, key: str) -> bool:
        """
        Check if a permission is granted.

        Args:
            key: Permission key (e.g. 'allow_file_write').

        Returns:
            True if allowed, False otherwise.
            Unknown keys default to True (fail-open for
            non-sensitive operations).
        """
        allowed = self._permissions.get(key, True)
        if not allowed:
            logger.warning("Permission DENIED: %s", key)
        return allowed

    def get_all(self) -> dict[str, bool]:
        """Return a copy of all current permissions."""
        return dict(self._permissions)
