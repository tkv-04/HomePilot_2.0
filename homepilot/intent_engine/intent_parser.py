"""
Smart intent parser for HomePilot.

3-layer intent matching system:
1. Regex patterns — exact structural matches (highest confidence)
2. Keyword scoring — matches based on keyword presence (medium confidence)
3. Fuzzy matching — difflib-based similarity matching (lower confidence)

Also includes:
- STT word corrections for common Vosk model errors
- New conversational intents (jokes, identity, capabilities, etc.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
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
# Layer 1: Regex intent patterns
# (intent_name, confidence, compiled_regex, slot_names)
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
        "control_device",
        0.85,
        re.compile(
            r"(?:can you |please )?(?:turn|switch|put|make)\s+(?:the\s+)?(.+?)\s+(on|off)",
            re.IGNORECASE,
        ),
        ["device", "action"],
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
        "set_timer",
        0.9,
        re.compile(
            r"timer\s+(?:for\s+)?(\d+\s+(?:second|minute|hour)s?)",
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
        "volume_control",
        0.85,
        re.compile(
            r"(?:increase|raise|louder)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "volume_control",
        0.85,
        re.compile(
            r"(?:decrease|lower|softer|quieter)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "system_shutdown",
        0.95,
        re.compile(
            r"(?:please\s+)?(?:shut\s*down|power\s+off|turn\s+off)\s+(?:the\s+)?(?:system|computer|pc|pi)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "system_reboot",
        0.95,
        re.compile(
            r"(?:please\s+)?(?:reboot|restart)\s+(?:the\s+)?(?:system|computer|pc|pi)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "system_status",
        0.9,
        re.compile(
            r"(?:what(?:'s|\s+is)\s+(?:the\s+)?)?(?:system\s+)?status|how(?:'s|\s+is)\s+(?:the\s+)?(?:system|pi|computer)",
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
            r"what(?:'s|\s+is)\s+(?:the\s+)?(.+?)(?:\s+(?:reading|value|status|right\s*now))?$",
            re.IGNORECASE,
        ),
        ["sensor"],
    ),
    # More flexible sensor queries (but exclude known intents)
    (
        "query_sensor",
        0.8,
        re.compile(
            r"(?:tell\s+me\s+)?(?:the\s+)?(?:current\s+)?((?:temperature|humidity|pressure|motion|battery|energy|power|sensor|weather)(?:\s+\w+)*)(?:\s+(?:reading|value|level))?\s*\??$",
            re.IGNORECASE,
        ),
        ["sensor"],
    ),

    # ── Conversational ──
    (
        "greeting",
        0.8,
        re.compile(
            r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|what's\s+up|howdy|namaste)(?:\s+jarvis)?[!.\s]*$",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "how_are_you",
        0.85,
        re.compile(
            r"(?:how\s+are\s+you|how(?:'s|\s+is)\s+it\s+going|how\s+do\s+you\s+feel|you\s+(?:ok|okay|alright))",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "identity",
        0.9,
        re.compile(
            r"(?:who\s+are\s+you|what(?:'s|\s+is)\s+your\s+name|introduce\s+yourself|what\s+are\s+you)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "capabilities",
        0.85,
        re.compile(
            r"(?:what\s+can\s+you\s+do|what\s+are\s+your\s+(?:abilities|features|capabilities)|help\s*$|what\s+(?:do\s+you|can\s+i)\s+(?:do|say|ask))",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "tell_joke",
        0.9,
        re.compile(
            r"(?:tell\s+(?:me\s+)?(?:a\s+)?joke|say\s+something\s+funny|make\s+me\s+laugh|joke\s*$|funny)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "compliment",
        0.85,
        re.compile(
            r"(?:you(?:'re|\s+are)\s+(?:awesome|great|amazing|smart|cool|the\s+best)|good\s+(?:job|work)|nice)",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "stop",
        0.95,
        re.compile(
            r"^(?:stop|cancel|shut\s+up|be\s+quiet|never\s*mind|that's?\s+(?:all|enough)|no\s*(?:thing)?|nothing)$",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "thank_you",
        0.8,
        re.compile(
            r"^(?:thanks?(?:\s+you)?|thank\s+you(?:\s+jarvis)?|cheers|much\s+appreciated)[!.\s]*$",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "time_query",
        0.95,
        re.compile(
            r"what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?time",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "date_query",
        0.95,
        re.compile(
            r"what(?:'s|\s+is)\s+(?:the\s+)?(?:today'?s?\s+)?date|what\s+day\s+is\s+it",
            re.IGNORECASE,
        ),
        [],
    ),
]


# ─────────────────────────────────────────────────────────────
# Layer 2: Keyword-based scoring
# Maps keywords → (intent_name, slot_key_if_any)
# ─────────────────────────────────────────────────────────────

_KEYWORD_INTENTS: dict[str, list[tuple[str, str, float]]] = {
    # keyword → list of (intent_name, slot_key, weight)
    "temperature": [("query_sensor", "sensor", 0.9)],
    "humidity": [("query_sensor", "sensor", 0.9)],
    "pressure": [("query_sensor", "sensor", 0.8)],
    "sensor": [("query_sensor", "sensor", 0.7)],
    "weather": [("query_sensor", "sensor", 0.8)],
    "motion": [("query_sensor", "sensor", 0.8)],
    "battery": [("query_sensor", "sensor", 0.8)],
    "energy": [("query_sensor", "sensor", 0.7)],
    "power": [("query_sensor", "sensor", 0.7)],

    "light": [("control_device", "device", 0.7)],
    "lights": [("control_device", "device", 0.7)],
    "lamp": [("control_device", "device", 0.7)],
    "fan": [("control_device", "device", 0.7)],
    "switch": [("control_device", "device", 0.6)],
    "plug": [("control_device", "device", 0.7)],
    "ac": [("control_device", "device", 0.7)],

    "timer": [("set_timer", "duration", 0.7)],
    "alarm": [("set_timer", "duration", 0.6)],
    "remind": [("set_reminder", "message", 0.7)],
    "reminder": [("set_reminder", "message", 0.7)],

    "volume": [("volume_control", "", 0.8)],
    "louder": [("volume_control", "", 0.8)],
    "quieter": [("volume_control", "", 0.8)],
    "mute": [("volume_control", "action", 0.9)],
    "unmute": [("volume_control", "action", 0.9)],

    "scene": [("run_scene", "scene", 0.8)],
    "movie": [("run_scene", "scene", 0.7)],
    "bedtime": [("run_scene", "scene", 0.7)],
    "goodnight": [("run_scene", "scene", 0.7)],

    "joke": [("tell_joke", "", 0.9)],
    "funny": [("tell_joke", "", 0.7)],
    "laugh": [("tell_joke", "", 0.7)],

    "time": [("time_query", "", 0.6)],
    "clock": [("time_query", "", 0.7)],
    "date": [("date_query", "", 0.7)],
    "day": [("date_query", "", 0.5)],

    "shutdown": [("system_shutdown", "", 0.8)],
    "reboot": [("system_reboot", "", 0.8)],
    "restart": [("system_reboot", "", 0.8)],
    "status": [("system_status", "", 0.7)],
    "cpu": [("system_status", "", 0.8)],
    "memory": [("system_status", "", 0.7)],
    "ram": [("system_status", "", 0.7)],

    "open": [("system_command", "application", 0.6)],
    "launch": [("system_command", "application", 0.7)],

    "hello": [("greeting", "", 0.8)],
    "hi": [("greeting", "", 0.8)],
    "hey": [("greeting", "", 0.7)],
    "namaste": [("greeting", "", 0.9)],

    "thanks": [("thank_you", "", 0.8)],
    "thank": [("thank_you", "", 0.7)],
    "who": [("identity", "", 0.5)],
    "help": [("capabilities", "", 0.7)],
    "can": [("capabilities", "", 0.3)],
}

# Action keywords that modify device commands
_ACTION_KEYWORDS = {"on", "off", "up", "down", "toggle", "start", "stop"}


# ─────────────────────────────────────────────────────────────
# Layer 3: Fuzzy match templates
# ─────────────────────────────────────────────────────────────

_FUZZY_TEMPLATES: list[tuple[str, str, dict[str, str]]] = [
    ("turn on the light", "control_device", {"action": "on", "device": "light"}),
    ("turn off the light", "control_device", {"action": "off", "device": "light"}),
    ("turn on the fan", "control_device", {"action": "on", "device": "fan"}),
    ("turn off the fan", "control_device", {"action": "off", "device": "fan"}),
    ("what is the temperature", "query_sensor", {"sensor": "temperature"}),
    ("what is the humidity", "query_sensor", {"sensor": "humidity"}),
    ("the room temperature", "query_sensor", {"sensor": "room temperature"}),
    ("room temperature", "query_sensor", {"sensor": "room temperature"}),
    ("set a timer for five minutes", "set_timer", {"duration": "5 minutes"}),
    ("set a timer for ten minutes", "set_timer", {"duration": "10 minutes"}),
    ("what time is it", "time_query", {}),
    ("what is the time", "time_query", {}),
    ("what is the date", "date_query", {}),
    ("what day is it", "date_query", {}),
    ("tell me a joke", "tell_joke", {}),
    ("who are you", "identity", {}),
    ("what can you do", "capabilities", {}),
    ("how are you", "how_are_you", {}),
    ("system status", "system_status", {}),
    ("open firefox", "system_command", {"application": "firefox"}),
    ("open chrome", "system_command", {"application": "chrome"}),
    ("hello jarvis", "greeting", {}),
    ("activate movie night", "run_scene", {"scene": "movie night"}),
    ("good night scene", "run_scene", {"scene": "good night"}),
]


class IntentParser:
    """
    Smart intent classifier with 3-layer matching.

    Layer 1: Regex pattern matching (exact, highest confidence)
    Layer 2: Keyword-based scoring (flexible, medium confidence)
    Layer 3: Fuzzy template matching (fallback, lower confidence)

    Also includes STT word corrections for common Vosk errors.
    """

    # Common misheard word corrections for Vosk model
    _WORD_CORRECTIONS: dict[str, str] = {
        "late": "light",
        "laid": "light",
        "lite": "light",
        "lied": "light",
        "lie": "light",
        "lacking": "locking",
        "look": "lock",
        "far": "fan",
        "swish": "switch",
        "sit": "set",
        "tome": "time",
        "fire fox": "firefox",
        "bisi": "vlc",
    }

    def __init__(self, confidence_threshold: float = 0.4) -> None:
        self.confidence_threshold = confidence_threshold

    def parse(self, text: str) -> Intent:
        """
        Parse a user utterance into an Intent using 3-layer matching.

        Args:
            text: Transcribed user speech.

        Returns:
            The best matching Intent, or an 'unknown' intent
            if confidence is below threshold.
        """
        text = text.strip()
        if not text:
            return Intent(name="unknown", confidence=0.0, raw_text=text)

        original_text = text

        # Post-process: correct common STT misrecognitions
        corrected = self._correct_transcript(text)
        if corrected != text:
            logger.debug("STT correction: '%s' -> '%s'", text, corrected)
            text = corrected

        # ── Layer 1: Regex matching (highest confidence) ──
        regex_result = self._regex_match(text)
        if regex_result and regex_result.confidence >= self.confidence_threshold:
            logger.info(
                "Intent [regex]: %s (conf=%.2f) slots=%s",
                regex_result.name, regex_result.confidence, regex_result.slots,
            )
            return regex_result

        # ── Layer 2: Keyword scoring (medium confidence) ──
        keyword_result = self._keyword_match(text)
        if keyword_result and keyword_result.confidence >= self.confidence_threshold:
            logger.info(
                "Intent [keyword]: %s (conf=%.2f) slots=%s",
                keyword_result.name, keyword_result.confidence, keyword_result.slots,
            )
            return keyword_result

        # ── Layer 3: Fuzzy template matching (lower confidence) ──
        fuzzy_result = self._fuzzy_match(text)
        if fuzzy_result and fuzzy_result.confidence >= self.confidence_threshold:
            logger.info(
                "Intent [fuzzy]: %s (conf=%.2f) slots=%s",
                fuzzy_result.name, fuzzy_result.confidence, fuzzy_result.slots,
            )
            return fuzzy_result

        logger.info("No intent matched for: '%s'", original_text)
        return Intent(name="unknown", confidence=0.0, raw_text=original_text)

    def _regex_match(self, text: str) -> Intent | None:
        """Layer 1: Try exact regex pattern matching."""
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

        return best_intent

    def _keyword_match(self, text: str) -> Intent | None:
        """
        Layer 2: Keyword-based scoring.

        Scores each possible intent based on how many
        relevant keywords appear in the text.
        """
        words = set(text.lower().split())
        intent_scores: dict[str, float] = {}
        intent_slots: dict[str, dict[str, str]] = {}

        for word in words:
            if word in _KEYWORD_INTENTS:
                for intent_name, slot_key, weight in _KEYWORD_INTENTS[word]:
                    intent_scores[intent_name] = (
                        intent_scores.get(intent_name, 0) + weight
                    )
                    # Extract slot value from remaining words
                    if slot_key and intent_name not in intent_slots:
                        slot_value = self._extract_slot_value(text, word, intent_name)
                        if slot_value:
                            intent_slots[intent_name] = {slot_key: slot_value}

        if not intent_scores:
            return None

        # Boost control_device when action keywords are present
        has_action = bool(words & _ACTION_KEYWORDS)
        if has_action and "control_device" in intent_scores:
            intent_scores["control_device"] += 0.5

        # Get the highest scoring intent
        best_intent_name = max(intent_scores, key=intent_scores.get)  # type: ignore
        raw_score = intent_scores[best_intent_name]

        # Normalize score to 0.0–0.85 range (keyword never beats regex)
        confidence = min(raw_score, 0.85)

        # Extract action keywords for device control
        slots = intent_slots.get(best_intent_name, {})
        if best_intent_name == "control_device":
            for word in words:
                if word in _ACTION_KEYWORDS:
                    slots["action"] = word
                    break

        return Intent(
            name=best_intent_name,
            confidence=confidence,
            slots=slots,
            raw_text=text,
        )

    def _fuzzy_match(self, text: str) -> Intent | None:
        """
        Layer 3: Fuzzy template matching using SequenceMatcher.

        Compares the text against known command templates
        and returns the closest match above a threshold.
        """
        text_lower = text.lower().strip()
        best_match: tuple[float, str, dict[str, str]] | None = None

        for template, intent_name, default_slots in _FUZZY_TEMPLATES:
            similarity = SequenceMatcher(None, text_lower, template).ratio()
            if similarity > 0.55:  # Minimum similarity threshold
                if best_match is None or similarity > best_match[0]:
                    best_match = (similarity, intent_name, default_slots)

        if best_match:
            similarity, intent_name, default_slots = best_match
            # Scale to 0.4–0.75 confidence range
            confidence = 0.4 + (similarity - 0.55) * (0.35 / 0.45)
            confidence = min(confidence, 0.75)

            return Intent(
                name=intent_name,
                confidence=confidence,
                slots=dict(default_slots),
                raw_text=text,
            )

        return None

    def _extract_slot_value(
        self, text: str, keyword: str, intent_name: str,
    ) -> str:
        """Extract a slot value from text near a keyword."""
        text_lower = text.lower()

        if intent_name == "query_sensor":
            # The whole phrase is the sensor query
            # Remove common question words
            cleaned = re.sub(
                r"^(?:what(?:'s|\s+is)\s+(?:the\s+)?|tell\s+me\s+(?:the\s+)?|"
                r"get\s+(?:the\s+)?|check\s+(?:the\s+)?)",
                "", text_lower, flags=re.IGNORECASE,
            ).strip()
            return cleaned or keyword

        if intent_name == "control_device":
            # Remove action words, return the device name
            cleaned = re.sub(
                r"(?:turn|switch|set|put|make)\s+(?:the\s+)?|"
                r"\s*(?:on|off|up|down)\s*",
                " ", text_lower, flags=re.IGNORECASE,
            ).strip()
            return cleaned or keyword

        if intent_name == "system_command":
            # Extract app name after "open/launch"
            match = re.search(
                r"(?:open|launch|start|run)\s+(?:the\s+)?(.+)",
                text_lower,
            )
            if match:
                return match.group(1).strip()

        return keyword

    def _correct_transcript(self, text: str) -> str:
        """
        Apply common word corrections to STT output.

        The Vosk model sometimes mishears certain words.
        This method applies known corrections.
        """
        words = text.lower().split()
        corrected = []
        for word in words:
            corrected.append(self._WORD_CORRECTIONS.get(word, word))
        return " ".join(corrected)
