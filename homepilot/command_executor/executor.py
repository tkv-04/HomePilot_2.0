"""
Central command executor for HomePilot.

Receives resolved intents and routes them to the
appropriate subsystem (OS control, Home Assistant,
timers, plugins). All commands pass through security
validation first.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, TYPE_CHECKING

from homepilot.entity_resolver.resolver import ResolvedEntities
from homepilot.intent_engine.intent_parser import Intent
from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.home_assistant.ha_client import HomeAssistantClient
    from homepilot.os_control.system_commands import SystemController
    from homepilot.plugins.plugin_manager import PluginManager
    from homepilot.security.validator import SecurityValidator
    from homepilot.timers.timer_manager import TimerManager

logger = get_logger("homepilot.executor")


class CommandExecutor:
    """
    Central command dispatcher.

    Routes classified intents to the correct subsystem
    after security validation. Returns a human-readable
    response for TTS output.
    """

    def __init__(
        self,
        system_controller: SystemController | None = None,
        ha_client: HomeAssistantClient | None = None,
        timer_manager: TimerManager | None = None,
        plugin_manager: PluginManager | None = None,
        security_validator: SecurityValidator | None = None,
        assistant_name: str = "Jarvis",
    ) -> None:
        self._system = system_controller
        self._ha = ha_client
        self._timers = timer_manager
        self._plugins = plugin_manager
        self._security = security_validator
        self._name = assistant_name
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the async event loop for HA calls."""
        self._event_loop = loop

    def execute(self, intent: Intent, entities: ResolvedEntities) -> str:
        """
        Execute a command based on the classified intent.

        Args:
            intent: The parsed intent with name, confidence, and slots.
            entities: Resolved entities from the intent slots.

        Returns:
            Human-readable response string for TTS.
        """
        # Security validation
        if self._security:
            ok, reason = self._security.validate_command(
                intent.name,
                intent.slots,
            )
            if not ok:
                logger.warning("Command blocked by security: %s", reason)
                return f"I can't do that. {reason}"

        # Route to the appropriate handler
        handler = self._HANDLERS.get(intent.name)
        if handler:
            return handler(self, intent, entities)

        # Try plugins
        if self._plugins:
            result = self._plugins.handle_intent(
                intent.name, intent.slots, entities,
            )
            if result:
                return result

        # Unknown intent
        return self._handle_unknown(intent, entities)

    # ─────────────────────────────────────────────────────
    # Intent Handlers
    # ─────────────────────────────────────────────────────

    def _handle_control_device(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle device on/off/toggle commands via Home Assistant."""
        if not self._ha:
            return "Home Assistant is not configured."

        device = entities.device_name or "device"
        action = entities.action or "toggle"

        # Try to find the entity in HA
        async def _do() -> str:
            entity_id = await self._ha.find_entity(device, entities.device_type)
            if not entity_id:
                return f"I couldn't find a device called '{device}' in Home Assistant."
            return await self._ha.control_device(
                entity_id, action, entities.brightness,
            )

        return self._run_async(_do())

    def _handle_dim_device(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle device brightness/dim commands."""
        if not self._ha:
            return "Home Assistant is not configured."

        device = entities.device_name or "light"
        brightness = entities.brightness or 50

        async def _do() -> str:
            entity_id = await self._ha.find_entity(device, "light")
            if not entity_id:
                return f"I couldn't find a light called '{device}'."
            return await self._ha.control_device(entity_id, "on", brightness)

        return self._run_async(_do())

    def _handle_set_timer(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle timer creation."""
        if not self._timers:
            return "Timer system is not available."

        duration = entities.duration_seconds
        if not duration or duration <= 0:
            return "I didn't catch the duration. How long should the timer be?"

        return self._timers.add_timer(
            duration_seconds=duration,
            message=entities.message or "",
        )

    def _handle_set_reminder(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle reminder creation (timer with message)."""
        return self._handle_set_timer(intent, entities)

    def _handle_cancel_timer(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle timer cancellation."""
        if not self._timers:
            return "Timer system is not available."
        return self._timers.cancel_timer()

    def _handle_list_timers(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle timer listing."""
        if not self._timers:
            return "Timer system is not available."
        return self._timers.list_timers()

    def _handle_system_command(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle application launch."""
        if not self._system:
            return "OS control is not available."
        app = entities.application or intent.slots.get("application", "")
        if not app:
            return "Which application would you like me to open?"
        return self._system.launch_application(app)

    def _handle_volume_control(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle volume up/down/mute/set."""
        if not self._system:
            return "OS control is not available."
        return self._system.volume_control(
            action=entities.action,
            level=entities.volume_level,
        )

    def _handle_system_shutdown(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle system shutdown."""
        if not self._system:
            return "OS control is not available."
        return self._system.system_shutdown()

    def _handle_system_reboot(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle system reboot."""
        if not self._system:
            return "OS control is not available."
        return self._system.system_reboot()

    def _handle_system_status(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle system status query."""
        if not self._system:
            return "OS control is not available."
        return self._system.get_system_status()

    def _handle_run_scene(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle scene/automation activation."""
        if not self._ha:
            return "Home Assistant is not configured."
        scene = entities.scene_name or ""
        if not scene:
            return "Which scene would you like me to activate?"

        async def _do() -> str:
            return await self._ha.run_scene(scene)

        return self._run_async(_do())

    def _handle_query_sensor(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle sensor queries."""
        if not self._ha:
            return "Home Assistant is not configured."
        sensor = entities.sensor_name or ""
        if not sensor:
            return "Which sensor would you like to check?"

        async def _do() -> str:
            return await self._ha.query_sensor(sensor)

        return self._run_async(_do())

    def _handle_greeting(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle greetings."""
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        return f"{greeting}! I'm {self._name}. How can I help you?"

    def _handle_stop(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle stop / cancel commands."""
        return "Okay, cancelled."

    def _handle_thank_you(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle thank you."""
        return "You're welcome! Let me know if you need anything else."

    def _handle_time_query(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle time query."""
        now = datetime.now()
        return f"It's currently {now.strftime('%I:%M %p')}."

    def _handle_date_query(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle date query."""
        now = datetime.now()
        return f"Today is {now.strftime('%A, %B %d, %Y')}."

    def _handle_unknown(self, intent: Intent, entities: ResolvedEntities) -> str:
        """Handle unrecognized commands."""
        return "I'm sorry, I didn't understand that. Could you try again?"

    # ─────────────────────────────────────────────────────
    # Handler routing table
    # ─────────────────────────────────────────────────────

    _HANDLERS: dict[str, Any] = {
        "control_device": _handle_control_device,
        "dim_device": _handle_dim_device,
        "set_timer": _handle_set_timer,
        "set_reminder": _handle_set_reminder,
        "cancel_timer": _handle_cancel_timer,
        "list_timers": _handle_list_timers,
        "system_command": _handle_system_command,
        "volume_control": _handle_volume_control,
        "system_shutdown": _handle_system_shutdown,
        "system_reboot": _handle_system_reboot,
        "system_status": _handle_system_status,
        "run_scene": _handle_run_scene,
        "query_sensor": _handle_query_sensor,
        "greeting": _handle_greeting,
        "stop": _handle_stop,
        "thank_you": _handle_thank_you,
        "time_query": _handle_time_query,
        "date_query": _handle_date_query,
    }

    def _run_async(self, coro: Any) -> str:
        """Run an async coroutine from sync context."""
        if self._event_loop and self._event_loop.is_running():
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(coro, self._event_loop)
            try:
                return future.result(timeout=15)
            except concurrent.futures.TimeoutError:
                return "The request timed out."
            except Exception as e:
                logger.error("Async execution error: %s", e)
                return f"An error occurred: {e}"
        else:
            try:
                return asyncio.run(coro)
            except Exception as e:
                logger.error("Async execution error: %s", e)
                return f"An error occurred: {e}"
