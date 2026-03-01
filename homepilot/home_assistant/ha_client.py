"""
Home Assistant integration client for HomePilot.

Async REST API client supporting:
- Light/switch/scene control
- Sensor queries
- Automation triggering
- Local API with Nabu Casa cloud fallback
- Encrypted token storage
"""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.config.settings import HomeAssistantConfig

logger = get_logger("homepilot.home_assistant")


class HomeAssistantClient:
    """
    Async client for the Home Assistant REST API.

    Connects via long-lived access token. Prefers local API;
    falls back to Nabu Casa cloud URL if local is unreachable.

    Usage:
        client = HomeAssistantClient(config)
        await client.connect()
        await client.call_service("light", "turn_on", {"entity_id": "light.kitchen"})
        await client.close()
    """

    def __init__(self, config: HomeAssistantConfig) -> None:
        self._config = config
        self._session: Any = None
        self._base_url: str = ""
        self._headers: dict[str, str] = {}
        self._connected: bool = False

    async def connect(self) -> bool:
        """
        Establish connection to Home Assistant.

        Tries the local URL first, then falls back to cloud URL.

        Returns:
            True if connected successfully.
        """
        import aiohttp

        if not self._config.enabled:
            logger.info("Home Assistant integration is disabled.")
            return False

        token = self._config.access_token
        if not token:
            logger.error("No Home Assistant access token configured.")
            return False

        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        connector = aiohttp.TCPConnector(ssl=self._config.verify_ssl)
        timeout = aiohttp.ClientTimeout(total=self._config.timeout)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
        )

        # Try local URL first
        if self._config.prefer_local and self._config.local_url:
            if await self._test_connection(self._config.local_url):
                self._base_url = self._config.local_url.rstrip("/")
                self._connected = True
                logger.info("Connected to Home Assistant (local): %s", self._base_url)
                return True

        # Fallback to cloud URL
        if self._config.cloud_url:
            if await self._test_connection(self._config.cloud_url):
                self._base_url = self._config.cloud_url.rstrip("/")
                self._connected = True
                logger.info("Connected to Home Assistant (cloud): %s", self._base_url)
                return True

        logger.error("Failed to connect to Home Assistant.")
        await self.close()
        return False

    async def _test_connection(self, url: str) -> bool:
        """Test if a HA URL is reachable."""
        try:
            async with self._session.get(
                f"{url.rstrip('/')}/api/",
                headers=self._headers,
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug("HA connection test failed for %s: %s", url, e)
            return False

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
    ) -> str:
        """
        Call a Home Assistant service.

        Args:
            domain: Service domain (e.g., 'light', 'switch', 'scene').
            service: Service name (e.g., 'turn_on', 'turn_off', 'toggle').
            service_data: Service data dict with entity_id and options.

        Returns:
            Human-readable status message.
        """
        if not self._connected:
            return "Not connected to Home Assistant."

        url = f"{self._base_url}/api/services/{domain}/{service}"
        try:
            async with self._session.post(
                url,
                headers=self._headers,
                json=service_data or {},
            ) as resp:
                if resp.status == 200:
                    logger.info("HA service called: %s/%s %s", domain, service, service_data)
                    return f"Done. {domain} {service} executed."
                else:
                    text = await resp.text()
                    logger.error("HA service error %d: %s", resp.status, text)
                    return f"Home Assistant returned an error: {resp.status}"
        except asyncio.TimeoutError:
            logger.error("HA service call timed out: %s/%s", domain, service)
            return "Home Assistant request timed out."
        except Exception as e:
            logger.error("HA service call failed: %s", e)
            return "Failed to communicate with Home Assistant."

    async def control_device(
        self,
        entity_id: str,
        action: str,
        brightness: int | None = None,
    ) -> str:
        """
        Control a device by entity ID.

        Args:
            entity_id: HA entity ID (e.g., 'light.kitchen').
            action: 'on', 'off', or 'toggle'.
            brightness: Brightness level 0-255 (for lights).

        Returns:
            Status message.
        """
        domain = entity_id.split(".")[0] if "." in entity_id else "light"
        service = {
            "on": "turn_on",
            "off": "turn_off",
            "toggle": "toggle",
        }.get(action, "toggle")

        data: dict[str, Any] = {"entity_id": entity_id}
        if brightness is not None and domain == "light":
            data["brightness"] = max(0, min(255, int(brightness * 2.55)))

        return await self.call_service(domain, service, data)

    async def get_state(self, entity_id: str) -> dict[str, Any] | None:
        """
        Get the current state of an entity.

        Args:
            entity_id: HA entity ID.

        Returns:
            State dict or None on failure.
        """
        if not self._connected:
            return None

        url = f"{self._base_url}/api/states/{entity_id}"
        try:
            async with self._session.get(url, headers=self._headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.error("HA state query error %d for %s", resp.status, entity_id)
                return None
        except Exception as e:
            logger.error("HA state query failed: %s", e)
            return None

    async def query_sensor(self, sensor_name: str) -> str:
        """
        Query a sensor's current reading.

        Args:
            sensor_name: Partial sensor name to search for.

        Returns:
            Human-readable sensor reading.
        """
        if not self._connected:
            return "Not connected to Home Assistant."

        url = f"{self._base_url}/api/states"
        try:
            async with self._session.get(url, headers=self._headers) as resp:
                if resp.status != 200:
                    return "Failed to query sensors."
                states = await resp.json()

            # Find matching sensor
            sensor_name_lower = sensor_name.lower()
            for state in states:
                eid: str = state.get("entity_id", "")
                friendly: str = state.get("attributes", {}).get("friendly_name", "")
                if (
                    sensor_name_lower in eid.lower()
                    or sensor_name_lower in friendly.lower()
                ):
                    value = state.get("state", "unknown")
                    unit = state.get("attributes", {}).get("unit_of_measurement", "")
                    name = friendly or eid
                    return f"{name} is {value} {unit}".strip()

            return f"I couldn't find a sensor matching '{sensor_name}'."

        except Exception as e:
            logger.error("Sensor query error: %s", e)
            return "Failed to query the sensor."

    async def run_scene(self, scene_name: str) -> str:
        """
        Activate a scene by name.

        Args:
            scene_name: Partial scene name to match.

        Returns:
            Status message.
        """
        if not self._connected:
            return "Not connected to Home Assistant."

        url = f"{self._base_url}/api/states"
        try:
            async with self._session.get(url, headers=self._headers) as resp:
                if resp.status != 200:
                    return "Failed to fetch scenes."
                states = await resp.json()

            scene_name_lower = scene_name.lower()
            for state in states:
                eid: str = state.get("entity_id", "")
                if eid.startswith("scene.") and scene_name_lower in eid.lower():
                    return await self.call_service("scene", "turn_on", {"entity_id": eid})

            # Also try automations
            for state in states:
                eid = state.get("entity_id", "")
                if eid.startswith("automation.") and scene_name_lower in eid.lower():
                    return await self.call_service("automation", "trigger", {"entity_id": eid})

            return f"I couldn't find a scene or automation matching '{scene_name}'."

        except Exception as e:
            logger.error("Scene activation error: %s", e)
            return "Failed to activate the scene."

    async def find_entity(self, name: str, device_type: str | None = None) -> str | None:
        """
        Find an entity ID by friendly name.

        Args:
            name: Partial device name from voice command.
            device_type: Optional HA domain filter (light, switch, etc.).

        Returns:
            Entity ID string, or None if not found.
        """
        if not self._connected:
            return None

        url = f"{self._base_url}/api/states"
        try:
            async with self._session.get(url, headers=self._headers) as resp:
                if resp.status != 200:
                    return None
                states = await resp.json()

            name_lower = name.lower()
            for state in states:
                eid: str = state.get("entity_id", "")
                friendly: str = state.get("attributes", {}).get("friendly_name", "")

                # Filter by domain if specified
                if device_type and not eid.startswith(f"{device_type}."):
                    continue

                if name_lower in eid.lower() or name_lower in friendly.lower():
                    return eid

            return None

        except Exception as e:
            logger.error("Entity search error: %s", e)
            return None

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._connected = False
            logger.info("Home Assistant client closed.")
