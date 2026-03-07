"""
Home Assistant tools for HomePilot agent.

Wraps HomeAssistantClient methods as agent-callable tools
with structured string return values.
"""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.home_assistant.ha_client import HomeAssistantClient

logger = get_logger("homepilot.tools.ha")

# Module-level references set by register_tools()
_ha_client: HomeAssistantClient | None = None
_event_loop: asyncio.AbstractEventLoop | None = None


def register_tools(
    router: "ToolRouter",
    ha_client: HomeAssistantClient | None = None,
    event_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """
    Register all Home Assistant tools with the tool router.

    Args:
        router: The ToolRouter instance.
        ha_client: The HomeAssistantClient instance.
        event_loop: The async event loop for running HA coroutines.
    """
    global _ha_client, _event_loop
    _ha_client = ha_client
    _event_loop = event_loop

    from homepilot.core.tool_router import ToolRouter

    router.register(
        name="turn_light_on",
        func=turn_light_on,
        description="Turn on a light in the home",
        parameter_descriptions={"entity_id": "Home Assistant entity ID (e.g. 'light.bedroom')"},
        permission_key="allow_ha_control",
    )
    router.register(
        name="turn_light_off",
        func=turn_light_off,
        description="Turn off a light in the home",
        parameter_descriptions={"entity_id": "Home Assistant entity ID (e.g. 'light.bedroom')"},
        permission_key="allow_ha_control",
    )
    router.register(
        name="set_temperature",
        func=set_temperature,
        description="Set the temperature of a thermostat/climate device",
        parameter_descriptions={
            "entity_id": "Home Assistant climate entity ID",
            "value": "Temperature value to set",
        },
        permission_key="allow_ha_control",
    )
    router.register(
        name="query_sensor",
        func=query_sensor,
        description="Query a sensor reading (temperature, humidity, etc.)",
        parameter_descriptions={"sensor_name": "Name of the sensor to query"},
        permission_key="allow_ha_control",
    )


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from sync context."""
    if not _event_loop:
        raise RuntimeError("No event loop available for Home Assistant calls.")
    future = asyncio.run_coroutine_threadsafe(coro, _event_loop)
    return future.result(timeout=15)


def _check_ha() -> str | None:
    """Check if HA is available. Returns error string or None."""
    if not _ha_client:
        return "Error: Home Assistant is not configured."
    if not _ha_client._base_url:
        return "Error: Home Assistant is not connected."
    return None


def turn_light_on(entity_id: str = "") -> str:
    """Turn on a light."""
    err = _check_ha()
    if err:
        return err
    if not entity_id:
        return "Error: Please specify an entity_id (e.g. 'light.bedroom')."

    try:
        result = _run_async(
            _ha_client.control_device(entity_id, action="on")
        )
        return result or f"Turned on {entity_id}."
    except Exception as e:
        return f"Error turning on light: {e}"


def turn_light_off(entity_id: str = "") -> str:
    """Turn off a light."""
    err = _check_ha()
    if err:
        return err
    if not entity_id:
        return "Error: Please specify an entity_id (e.g. 'light.bedroom')."

    try:
        result = _run_async(
            _ha_client.control_device(entity_id, action="off")
        )
        return result or f"Turned off {entity_id}."
    except Exception as e:
        return f"Error turning off light: {e}"


def set_temperature(entity_id: str = "", value: float | str = "") -> str:
    """Set a thermostat temperature."""
    err = _check_ha()
    if err:
        return err
    if not entity_id:
        return "Error: Please specify a climate entity_id."

    try:
        temp = float(value)
    except (ValueError, TypeError):
        return "Error: Invalid temperature value."

    try:
        result = _run_async(
            _ha_client.call_service(
                domain="climate",
                service="set_temperature",
                service_data={
                    "entity_id": entity_id,
                    "temperature": temp,
                },
            )
        )
        return result or f"Set {entity_id} to {temp}°."
    except Exception as e:
        return f"Error setting temperature: {e}"


def query_sensor(sensor_name: str = "") -> str:
    """Query a sensor reading."""
    err = _check_ha()
    if err:
        return err
    if not sensor_name:
        return "Error: Please specify a sensor name."

    try:
        result = _run_async(
            _ha_client.query_sensor(sensor_name)
        )
        return result or f"No data available for sensor '{sensor_name}'."
    except Exception as e:
        return f"Error querying sensor: {e}"
