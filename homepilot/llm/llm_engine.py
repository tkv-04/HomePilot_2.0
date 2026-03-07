"""
Local LLM engine for HomePilot.

Connects to Ollama (local LLM server) to provide intelligent
natural language understanding as an optional smart fallback.

Works on all devices:
- RPi 4 (2GB): qwen2.5:0.5b (~400MB)
- RPi 4 (4GB): qwen2.5:1.5b (~1GB)
- Desktop/Laptop: any larger model

If Ollama is not running, HomePilot falls back to
regex + keyword + fuzzy matching (no crash).
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.llm")

# System prompt that instructs the LLM to classify intents
_SYSTEM_PROMPT = """You are a smart home voice assistant intent classifier. Your job is to understand what the user wants and classify it into an intent.

AVAILABLE INTENTS:
- control_device: Turn on/off/toggle lights, fans, switches, plugs, AC (slots: action, device, room)
- dim_device: Set brightness of a light (slots: device, brightness)
- query_sensor: Ask about temperature, humidity, or any sensor reading (slots: sensor)
- set_timer: Set a countdown timer (slots: duration)
- cancel_timer: Cancel a running timer
- list_timers: List active timers
- system_command: Open/launch an application (slots: application)
- volume_control: Change volume up/down/mute/set level (slots: action, level)
- system_shutdown: Shut down the computer
- system_reboot: Restart the computer
- system_status: Check CPU/RAM/disk usage
- run_scene: Activate a Home Assistant scene (slots: scene)
- time_query: Ask what time it is
- date_query: Ask what date it is
- greeting: Hello/hi/hey
- tell_joke: Tell a joke or something funny
- identity: Who are you / what are you
- capabilities: What can you do / help
- how_are_you: How are you doing
- thank_you: Thanks / thank you
- stop: Stop / cancel / never mind
- compliment: You're awesome / great job
- unknown: Cannot determine the intent

IMPORTANT RULES:
1. The input may contain speech recognition errors. Try to guess the intended meaning.
2. Respond ONLY with a JSON object, nothing else.
3. Format: {"intent": "intent_name", "confidence": 0.0-1.0, "slots": {}, "response": "optional direct response"}
4. For unknown intents, provide a helpful response in the "response" field.
5. Keep responses short and conversational.

EXAMPLES:
User: "the fast" (probably meant "the time" or "what time is it")
{"intent": "time_query", "confidence": 0.6, "slots": {}, "response": ""}

User: "turn off the late" (probably meant "turn off the light")
{"intent": "control_device", "confidence": 0.8, "slots": {"action": "off", "device": "light"}, "response": ""}

User: "what's the weather like"
{"intent": "query_sensor", "confidence": 0.7, "slots": {"sensor": "weather"}, "response": ""}

User: "tell me something interesting"
{"intent": "unknown", "confidence": 0.3, "slots": {}, "response": "I'm a smart home assistant. I can control your devices, set timers, and tell you sensor readings. Try asking me to turn on a light!"}
"""


class LLMEngine:
    """
    Optional Ollama-powered LLM engine for smart NLU.

    Auto-detects if Ollama is running. If not, all methods
    return None gracefully — no crashes, no dependencies.

    Usage:
        llm = LLMEngine()
        if llm.is_available():
            result = llm.classify_intent("the fast")
            # result = {"intent": "time_query", "confidence": 0.6, ...}
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:0.5b",
        timeout: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._available: bool | None = None  # Lazy detection

    def is_available(self) -> bool:
        """Check if Ollama is running and the model exists."""
        if self._available is not None:
            return self._available

        try:
            url = f"{self._base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("name", "") for m in data.get("models", [])]

                # Check if any model matches (with or without :latest tag)
                model_base = self._model.split(":")[0]
                found = any(
                    m.startswith(model_base) for m in models
                )

                if found:
                    logger.info(
                        "🧠 LLM available: Ollama + %s",
                        self._model,
                    )
                    self._available = True
                else:
                    available_models = ", ".join(models[:5]) or "none"
                    logger.info(
                        "LLM model '%s' not found. Available: %s. "
                        "Pull it with: ollama pull %s",
                        self._model, available_models, self._model,
                    )
                    # Still usable if ANY model exists
                    if models:
                        self._model = models[0]
                        logger.info(
                            "🧠 Using available model: %s", self._model,
                        )
                        self._available = True
                    else:
                        self._available = False
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            logger.info("LLM not available (Ollama not running): %s", e)
            self._available = False

        return self._available

    def classify_intent(self, text: str) -> dict[str, Any] | None:
        """
        Use the LLM to classify a user utterance into an intent.

        Args:
            text: Transcribed user speech (may be garbled).

        Returns:
            Dict with keys: intent, confidence, slots, response.
            None if LLM is unavailable or fails.
        """
        if not self.is_available():
            return None

        try:
            payload = json.dumps({
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 200,
                },
            }).encode("utf-8")

            url = f"{self._base_url}/api/chat"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode())

            content = data.get("message", {}).get("content", "")
            logger.debug("LLM raw response: %s", content[:200])

            # Parse JSON from the response
            result = self._parse_llm_response(content)
            if result:
                logger.info(
                    "LLM classified: intent=%s conf=%.2f slots=%s",
                    result.get("intent"),
                    result.get("confidence", 0),
                    result.get("slots", {}),
                )
            return result

        except (urllib.error.URLError, OSError, TimeoutError) as e:
            logger.warning("LLM request failed: %s", e)
            return None
        except Exception as e:
            logger.warning("LLM unexpected error: %s", e)
            return None

    def generate_response(self, prompt: str) -> str | None:
        """
        Generate a free-form response from the LLM.

        Used for conversational queries that don't match
        any specific intent.

        Args:
            prompt: The user's query.

        Returns:
            Response string, or None if unavailable.
        """
        if not self.is_available():
            return None

        try:
            payload = json.dumps({
                "model": self._model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are Jarvis, a friendly smart home voice assistant. "
                            "Keep responses very short (1-2 sentences max). "
                            "Be helpful and conversational. "
                            "You run locally — no cloud, full privacy."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 100,
                },
            }).encode("utf-8")

            url = f"{self._base_url}/api/chat"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode())

            content = data.get("message", {}).get("content", "").strip()
            return content or None

        except Exception as e:
            logger.warning("LLM generate failed: %s", e)
            return None

    @staticmethod
    def _parse_llm_response(content: str) -> dict[str, Any] | None:
        """
        Extract JSON from the LLM response.

        The LLM might wrap JSON in markdown code blocks or
        include extra text. This method handles those cases.
        """
        # Try direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        import re
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object in the text
        json_match = re.search(r"\{[^{}]*\}", content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse LLM response as JSON: %s", content[:100])
        return None
