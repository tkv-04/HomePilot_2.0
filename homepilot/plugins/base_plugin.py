"""
Plugin base class for HomePilot.

All plugins must extend BasePlugin and implement
the required methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class PluginInfo:
    """Plugin metadata."""
    name: str
    version: str
    description: str
    author: str = ""
    intents: list[str] | None = None  # Intents this plugin handles


class BasePlugin(ABC):
    """
    Abstract base class for HomePilot plugins.

    Every plugin must subclass this and implement:
    - `info()` — return plugin metadata
    - `can_handle(intent_name)` — whether this plugin handles an intent
    - `execute(intent_name, slots, entities)` — execute the command

    Plugins are discovered from the configured plugins directory.
    Each plugin file should contain a single class inheriting BasePlugin.
    """

    @abstractmethod
    def info(self) -> PluginInfo:
        """Return plugin metadata."""
        ...

    @abstractmethod
    def can_handle(self, intent_name: str) -> bool:
        """
        Check if this plugin can handle the given intent.

        Args:
            intent_name: The classified intent name.

        Returns:
            True if this plugin should handle this intent.
        """
        ...

    @abstractmethod
    def execute(
        self,
        intent_name: str,
        slots: dict[str, Any],
        entities: Any | None = None,
    ) -> str:
        """
        Execute a command for the given intent.

        Args:
            intent_name: The classified intent name.
            slots: Raw slots from the intent parser.
            entities: Resolved entities (ResolvedEntities object).

        Returns:
            Human-readable response string.
        """
        ...

    def on_load(self) -> None:
        """Called when the plugin is loaded. Override for setup."""
        pass

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Override for cleanup."""
        pass
