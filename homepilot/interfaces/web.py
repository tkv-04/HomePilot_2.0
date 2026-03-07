"""
Web interface placeholder for HomePilot agent.

This module is a placeholder for a future web-based
interface. Currently provides a minimal status endpoint.
"""

from __future__ import annotations

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.web")


class WebInterface:
    """
    Placeholder web interface.

    Future implementation will provide:
    - WebSocket-based real-time chat
    - Tool execution visualization
    - Memory and history browsing
    - Configuration management
    """

    def __init__(self, agent=None, host: str = "0.0.0.0", port: int = 8080) -> None:
        self._agent = agent
        self._host = host
        self._port = port
        logger.info("Web interface placeholder initialized (not yet implemented)")

    def start(self) -> None:
        """Start the web server (not yet implemented)."""
        logger.warning(
            "Web interface is a placeholder. "
            "Use --mode cli for the command-line interface."
        )
