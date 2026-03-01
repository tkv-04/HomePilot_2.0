"""
Rule-based intent parser for HomePilot.

Classifies user commands into intents using regex patterns.
Zero dependencies, instant inference, perfect for structured
smart-home and system commands. No GPU required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.intent")


@dataclass
class Intent:
    """
    Parsed intent from a user utterance.

    Attributes:
        name: Intent identifier (e.g., 'control_device', 'set_timer').
        confidence: Confidence score 0.0–1.0.
        slots: Extracted slots/entities as a dict.
        raw_text: Original user utterance.
    """
    name: str
    confidence: float
    slots: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""


# ─────────────────────────────────────────────────────────────
# Intent pattern definitions
# Each entry: (intent_name, confidence, compiled_regex, slot_extractors)
# ─────────────────────────────────────────────────────────────

_INTENT_PATTERNS: list[tuple[str, float, re.Pattern, list[str]]] = [
    # ── Device Control ──
    (
        "control_device",
        0.9,
        re.compile(
            r"(?:turn|switch|set)\s+(on|off|up|down)\s+(?:the\s+)?(.+?)(?:\s+in\s+(?:the\s+)?(.+))?$",
            re.IGNORECASE,
        ),
        ["action", "device", "room"],
    ),
    (
        "control_device",
        0.9,
        re.compile(
            r"(?:turn|switch|set)\s+(?:the\s+)?(.+?)\s+(on|off|up|down)(?:\s+in\s+(?:the\s+)?(.+))?$",
            re.IGNORECASE,
        ),
        ["device", "action", "room"],
    ),
    (
        "dim_device",
        0.85,
        re.compile(
            r"(?:set|dim|change)\s+(?:the\s+)?(.+?)\s+(?:to|at)\s+(\d+)\s*(?:percent|%)?",
            re.IGNORECASE,
        ),
        ["device", "brightness"],
    ),

    # ── Timers ──
    (
        "set_timer",
        0.95,
        re.compile(
            r"(?:set|start|create)\s+(?:a\s+)?timer\s+(?:for\s+)?(.+)",
            re.IGNORECASE,
        ),
        ["duration"],
    ),
    (
        "set_reminder",
        0.9,
        re.compile(
            r"remind\s+me\s+(?:in\s+)?(.+?)\s+(?:to\s+)(.+)",
            re.IGNORECASE,
        ),
        ["duration", "message"],
    ),
    (
        "cancel_timer",
        0.9,
        re.compile(
            r"(?:cancel|stop|delete|remove)\s+(?:the\s+)?(?:timer|all\s+timers)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "list_timers",
        0.9,
        re.compile(
            r"(?:list|show|what|how\s+many)\s+(?:are\s+)?(?:the\s+)?(?:active\s+)?timers",
            re.IGNORECASE,
        ),
        [],
    ),

    # ── System Commands ──
    (
        "system_command",
        0.9,
        re.compile(
            r"(?:open|launch|start|run)\s+(?:the\s+)?(.+)",
            re.IGNORECASE,
        ),
        ["application"],
    ),
    (
        "volume_control",
        0.9,
        re.compile(
            r"(?:set\s+)?(?:the\s+)?volume\s+(?:to\s+)?(\d+)(?:\s*(?:percent|%))?",
            re.IGNORECASE,
        ),
        ["level"],
    ),
    (
        "volume_control",
        0.85,
        re.compile(
            r"(?:turn\s+)?(?:the\s+)?volume\s+(up|down)",
            re.IGNORECASE,
        ),
        ["direction"],
    ),
    (
        "volume_control",
        0.85,
        re.compile(
            r"(mute|unmute)(?:\s+(?:the\s+)?(?:volume|sound|audio))?",
            re.IGNORECASE,
        ),
        ["action"],
    ),
    (
        "system_shutdown",
        0.95,
        re.compile(
            r"(?:please\s+)?(?:shut\s*down|power\s+off|turn\s+off)\s+(?:the\s+)?(?:system|computer|pi)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "system_reboot",
        0.95,
        re.compile(
            r"(?:please\s+)?(?:reboot|restart)\s+(?:the\s+)?(?:system|computer|pi)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "system_status",
        0.9,
        re.compile(
            r"(?:what(?:'s|\s+is)\s+(?:the\s+)?)?(?:system\s+)?status|how(?:'s|\s+is)\s+(?:the\s+)?(?:system|pi)",
            re.IGNORECASE,
        ),
        [],
    ),

    # ── Home Assistant Scenes / Automations ──
    (
        "run_scene",
        0.9,
        re.compile(
            r"(?:run|activate|trigger|execute|start)\s+(?:the\s+)?(?:scene\s+)?(.+?)(?:\s+scene)?$",
            re.IGNORECASE,
        ),
        ["scene"],
    ),
    (
        "query_sensor",
        0.85,
        re.compile(
            r"what(?:'s|\s+is)\s+(?:the\s+)?(.+?)(?:\s+(?:reading|value|status|temperature|level))?$",
            re.IGNORECASE,
        ),
        ["sensor"],
    ),

    # ── General / Fallback ──
    (
        "greeting",
        0.8,
        re.compile(
            r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|what's\s+up)(?:\s+jarvis)?[!.\s]*$",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "stop",
        0.95,
        re.compile(
            r"^(?:stop|cancel|shut\s+up|be\s+quiet|never\s*mind|that's?\s+(?:all|enough))$",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "thank_you",
        0.8,
        re.compile(
            r"^(?:thanks?(?:\s+you)?|thank\s+you(?:\s+jarvis)?|cheers)[!.\s]*$",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "time_query",
        0.9,
        re.compile(
            r"what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?time",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "date_query",
        0.9,
        re.compile(
            r"what(?:'s|\s+is)\s+(?:the\s+)?(?:today'?s?\s+)?date|what\s+day\s+is\s+it",
            re.IGNORECASE,
        ),
        [],
    ),
]


class IntentParser:
    """
    Rule-based intent classifier.

    Matches user utterances against a library of regex patterns
    and returns the best matching Intent with extracted slots.
    """

    def __init__(self, confidence_threshold: float = 0.5) -> None:
        self.confidence_threshold = confidence_threshold

    def parse(self, text: str) -> Intent:
        """
        Parse a user utterance into an Intent.

        Args:
            text: Transcribed user speech.

        Returns:
            The best matching Intent, or a 'unknown' intent
            if confidence is below threshold.
        """
        text = text.strip()
        if not text:
            return Intent(name="unknown", confidence=0.0, raw_text=text)

        best_intent: Intent | None = None

        for intent_name, confidence, pattern, slot_names in _INTENT_PATTERNS:
            match = pattern.search(text)
            if match:
                slots: dict[str, Any] = {}
                for i, slot_name in enumerate(slot_names):
                    group_idx = i + 1
                    if group_idx <= len(match.groups()):
                        value = match.group(group_idx)
                        if value:
                            slots[slot_name] = value.strip()

                candidate = Intent(
                    name=intent_name,
                    confidence=confidence,
                    slots=slots,
                    raw_text=text,
                )

                if best_intent is None or candidate.confidence > best_intent.confidence:
                    best_intent = candidate

        if best_intent and best_intent.confidence >= self.confidence_threshold:
            logger.info(
                "Intent: %s (conf=%.2f) slots=%s",
                best_intent.name,
                best_intent.confidence,
                best_intent.slots,
            )
            return best_intent

        logger.info("No intent matched for: '%s'", text)
        return Intent(name="unknown", confidence=0.0, raw_text=text)
