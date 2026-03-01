"""
Example Plugin: Weather Responses (Offline)

Demonstrates how to create a HomePilot skill plugin.
This plugin provides basic offline weather responses
from a static knowledge base.

To create your own plugin:
1. Create a .py file in the plugins/ directory
2. Subclass BasePlugin
3. Implement info(), can_handle(), and execute()
4. Restart HomePilot or reload plugins
"""

from __future__ import annotations

import random
from typing import Any

from homepilot.plugins.base_plugin import BasePlugin, PluginInfo


class WeatherPlugin(BasePlugin):
    """
    Example plugin that responds to weather-related queries
    with friendly offline responses.
    """

    # Offline weather tips — no API needed!
    _RESPONSES = [
        "I don't have access to live weather data offline, but I'd recommend checking out the window!",
        "Since I'm running offline, I can't check the weather right now. Try asking me when we have internet.",
        "I'm not connected to the internet right now, so I can't fetch weather data. But I can control your smart home!",
    ]

    _INDOOR_TIPS = [
        "Here's a tip: if you have a temperature sensor connected to Home Assistant, ask me 'What's the temperature?'",
        "Pro tip: you can set up a local weather station with Home Assistant to get weather data offline!",
    ]

    def info(self) -> PluginInfo:
        return PluginInfo(
            name="Weather Plugin",
            version="1.0.0",
            description="Offline weather query responses (example plugin)",
            author="HomePilot",
            intents=["weather_query"],
        )

    def can_handle(self, intent_name: str) -> bool:
        return intent_name == "weather_query"

    def execute(
        self,
        intent_name: str,
        slots: dict[str, Any],
        entities: Any | None = None,
    ) -> str:
        response = random.choice(self._RESPONSES)
        tip = random.choice(self._INDOOR_TIPS)
        return f"{response} {tip}"
