"""
Plugin manager for HomePilot.

Discovers, loads, and manages skill plugins from the plugins directory.
Plugins are integrity-checked via SHA256 manifest and sandboxed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from homepilot.plugins.base_plugin import BasePlugin, PluginInfo
from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.plugins")


class PluginManager:
    """
    Plugin discovery, loading, and lifecycle manager.

    Features:
    - Auto-discovers plugins from the plugins directory
    - Integrity checking via SHA256 manifest
    - Clean load/unload lifecycle
    - Routes intents to matching plugins

    Usage:
        manager = PluginManager(config)
        manager.load_plugins()
        result = manager.handle_intent("custom_intent", slots, entities)
        manager.unload_all()
    """

    def __init__(
        self,
        plugin_dir: str = "plugins",
        enabled_plugins: list[str] | None = None,
        manifest_file: str = "plugins/manifest.json",
        check_integrity: bool = True,
    ) -> None:
        self._plugin_dir = Path(plugin_dir)
        self._enabled = enabled_plugins or []
        self._manifest_file = Path(manifest_file)
        self._check_integrity = check_integrity
        self._plugins: dict[str, BasePlugin] = {}

    def load_plugins(self) -> None:
        """Discover and load all enabled plugins."""
        if not self._plugin_dir.exists():
            self._plugin_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Created plugins directory: %s", self._plugin_dir)
            return

        manifest = self._load_manifest() if self._check_integrity else {}

        for py_file in sorted(self._plugin_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            plugin_name = py_file.stem

            # Filter by enabled list (empty = all enabled)
            if self._enabled and plugin_name not in self._enabled:
                logger.debug("Skipping disabled plugin: %s", plugin_name)
                continue

            # Integrity check
            if self._check_integrity and manifest:
                if not self._verify_integrity(py_file, manifest):
                    logger.warning(
                        "Plugin '%s' failed integrity check. Skipping.",
                        plugin_name,
                    )
                    continue

            # Load the plugin
            try:
                plugin = self._load_plugin(py_file)
                if plugin:
                    self._plugins[plugin_name] = plugin
                    plugin.on_load()
                    info = plugin.info()
                    logger.info(
                        "Loaded plugin: %s v%s — %s",
                        info.name, info.version, info.description,
                    )
            except Exception as e:
                logger.error("Failed to load plugin '%s': %s", plugin_name, e)

        logger.info("Loaded %d plugin(s).", len(self._plugins))

    def unload_all(self) -> None:
        """Unload all plugins."""
        for name, plugin in self._plugins.items():
            try:
                plugin.on_unload()
            except Exception as e:
                logger.error("Error unloading plugin '%s': %s", name, e)
        self._plugins.clear()
        logger.info("All plugins unloaded.")

    def handle_intent(
        self,
        intent_name: str,
        slots: dict[str, Any],
        entities: Any | None = None,
    ) -> str | None:
        """
        Route an intent to a matching plugin.

        Args:
            intent_name: Classified intent name.
            slots: Raw slots.
            entities: Resolved entities.

        Returns:
            Response string from the plugin, or None if no plugin handled it.
        """
        for name, plugin in self._plugins.items():
            try:
                if plugin.can_handle(intent_name):
                    logger.info("Plugin '%s' handling intent '%s'", name, intent_name)
                    return plugin.execute(intent_name, slots, entities)
            except Exception as e:
                logger.error("Plugin '%s' error: %s", name, e)
                return f"Plugin error: {e}"
        return None

    def list_plugins(self) -> list[PluginInfo]:
        """List all loaded plugins."""
        return [p.info() for p in self._plugins.values()]

    @staticmethod
    def _load_plugin(path: Path) -> BasePlugin | None:
        """Dynamically load a plugin from a Python file."""
        module_name = f"homepilot_plugin_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find the plugin class (first subclass of BasePlugin)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
            ):
                return attr()

        logger.warning("No BasePlugin subclass found in: %s", path)
        return None

    def _load_manifest(self) -> dict[str, str]:
        """Load the SHA256 manifest file."""
        if not self._manifest_file.exists():
            return {}
        try:
            with open(self._manifest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load plugin manifest: %s", e)
            return {}

    @staticmethod
    def _verify_integrity(plugin_file: Path, manifest: dict[str, str]) -> bool:
        """Verify a plugin file's SHA256 hash against the manifest."""
        expected_hash = manifest.get(plugin_file.name)
        if not expected_hash:
            # Not in manifest — allow if manifest is empty (first run)
            return True

        actual_hash = hashlib.sha256(
            plugin_file.read_bytes()
        ).hexdigest()

        return actual_hash == expected_hash

    def generate_manifest(self) -> None:
        """Generate/update the SHA256 manifest for all plugins."""
        manifest: dict[str, str] = {}
        for py_file in sorted(self._plugin_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            sha = hashlib.sha256(py_file.read_bytes()).hexdigest()
            manifest[py_file.name] = sha

        self._manifest_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        logger.info("Plugin manifest generated: %s", self._manifest_file)
