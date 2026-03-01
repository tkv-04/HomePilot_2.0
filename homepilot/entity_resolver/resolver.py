"""
Entity resolver for HomePilot.

Extracts and normalizes entities from intent slots:
- Durations (e.g., "5 minutes" → 300 seconds)
- Device names (e.g., "living room light" → normalized)
- Room names
- Application names
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.entity_resolver")

# Duration patterns: number + unit
_DURATION_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(seconds?|secs?|s|"
    r"minutes?|mins?|m|"
    r"hours?|hrs?|h|"
    r"days?|d)",
    re.IGNORECASE,
)

_UNIT_TO_SECONDS: dict[str, float] = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}

# Common aliases for device names
_DEVICE_ALIASES: dict[str, str] = {
    "light": "light",
    "lights": "light",
    "lamp": "light",
    "lamps": "light",
    "fan": "fan",
    "fans": "fan",
    "switch": "switch",
    "plug": "switch",
    "ac": "climate",
    "air conditioner": "climate",
    "heater": "climate",
    "thermostat": "climate",
    "tv": "media_player",
    "television": "media_player",
    "speaker": "media_player",
    "lock": "lock",
    "door lock": "lock",
    "garage": "cover",
    "garage door": "cover",
    "blinds": "cover",
    "curtain": "cover",
    "curtains": "cover",
    "camera": "camera",
}


@dataclass
class ResolvedEntities:
    """
    Container for all resolved entities from an intent.

    Attributes:
        duration_seconds: Total duration in seconds (for timers).
        device_name: Normalized device name.
        device_type: Device type category (light, switch, etc.).
        room: Room/area name.
        action: Action to perform (on, off, up, down, etc.).
        application: Application name (for OS commands).
        brightness: Brightness level 0-100.
        volume_level: Volume level 0-100.
        scene_name: Scene/automation name.
        sensor_name: Sensor entity name.
        message: Reminder message text.
        extra: Any extra extracted data.
    """
    duration_seconds: float | None = None
    device_name: str | None = None
    device_type: str | None = None
    room: str | None = None
    action: str | None = None
    application: str | None = None
    brightness: int | None = None
    volume_level: int | None = None
    scene_name: str | None = None
    sensor_name: str | None = None
    message: str | None = None
    extra: dict[str, Any] | None = None


class EntityResolver:
    """
    Resolves and normalizes entities from intent slots.

    Takes raw slot values from the IntentParser and produces
    structured ResolvedEntities for the command executor.
    """

    def resolve(self, intent_name: str, slots: dict[str, Any]) -> ResolvedEntities:
        """
        Resolve entities from intent slots.

        Args:
            intent_name: The classified intent name.
            slots: Raw slot values from the intent parser.

        Returns:
            ResolvedEntities with normalized values.
        """
        entities = ResolvedEntities()

        # Duration parsing
        if "duration" in slots:
            entities.duration_seconds = self._parse_duration(slots["duration"])

        # Device resolution
        if "device" in slots:
            device_raw = slots["device"].lower().strip()
            entities.device_name = device_raw
            entities.device_type = self._resolve_device_type(device_raw)

        # Room
        if "room" in slots:
            entities.room = slots["room"].strip().lower()

        # Action
        if "action" in slots:
            entities.action = slots["action"].strip().lower()

        # Application
        if "application" in slots:
            entities.application = slots["application"].strip().lower()

        # Brightness
        if "brightness" in slots:
            try:
                entities.brightness = max(0, min(100, int(slots["brightness"])))
            except (ValueError, TypeError):
                pass

        # Volume
        if "level" in slots:
            try:
                entities.volume_level = max(0, min(100, int(slots["level"])))
            except (ValueError, TypeError):
                pass
        if "direction" in slots:
            entities.action = slots["direction"].strip().lower()

        # Scene
        if "scene" in slots:
            entities.scene_name = slots["scene"].strip().lower()

        # Sensor
        if "sensor" in slots:
            entities.sensor_name = slots["sensor"].strip().lower()

        # Reminder message
        if "message" in slots:
            entities.message = slots["message"].strip()

        logger.debug("Resolved entities: %s", entities)
        return entities

    @staticmethod
    def _parse_duration(text: str) -> float | None:
        """
        Parse a natural language duration string into seconds.

        Args:
            text: Duration text (e.g., "5 minutes", "1 hour 30 minutes").

        Returns:
            Total seconds, or None if no duration found.
        """
        matches = _DURATION_PATTERN.findall(text)
        if not matches:
            # Try bare number (assume minutes)
            bare = re.match(r"^(\d+)$", text.strip())
            if bare:
                return float(bare.group(1)) * 60
            return None

        total = 0.0
        for value_str, unit in matches:
            multiplier = _UNIT_TO_SECONDS.get(unit.lower(), 60)
            total += float(value_str) * multiplier

        return total if total > 0 else None

    @staticmethod
    def _resolve_device_type(device_name: str) -> str | None:
        """
        Infer the HA device type from a device name.

        Args:
            device_name: Raw device name from user speech.

        Returns:
            Device type category, or None if unknown.
        """
        name_lower = device_name.lower()
        for alias, device_type in _DEVICE_ALIASES.items():
            if alias in name_lower:
                return device_type
        return None
