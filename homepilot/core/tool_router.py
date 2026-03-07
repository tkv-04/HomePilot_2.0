"""
Dynamic tool registry and router for HomePilot agent.

Tools are registered with a name, callable, description,
and optional permission key. The router checks permissions
and security before executing any tool.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from homepilot.core.permissions import PermissionManager
from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.tool_router")


@dataclass
class ToolDefinition:
    """Metadata for a registered tool."""
    name: str
    func: Callable[..., str]
    description: str
    parameter_descriptions: dict[str, str] = field(default_factory=dict)
    permission_key: str | None = None


class ToolRouter:
    """
    Central tool registry and executor.

    Tools are registered at startup. When the agent requests
    a tool call, the router:
    1. Validates the tool exists
    2. Checks permissions via PermissionManager
    3. Executes the tool function
    4. Returns the structured result

    Usage:
        router = ToolRouter(permission_manager)
        router.register("cpu_usage", cpu_usage_fn, "Get CPU usage")
        result = router.execute("cpu_usage", {})
    """

    def __init__(self, permission_manager: PermissionManager) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._permissions = permission_manager

    def register(
        self,
        name: str,
        func: Callable[..., str],
        description: str,
        parameter_descriptions: dict[str, str] | None = None,
        permission_key: str | None = None,
    ) -> None:
        """
        Register a tool.

        Args:
            name: Unique tool name (e.g. 'cpu_usage').
            func: Callable that takes **kwargs and returns a string result.
            description: Human-readable description for the LLM.
            parameter_descriptions: Dict of param_name → description.
            permission_key: Permission key to check (e.g. 'allow_file_write').
        """
        self._tools[name] = ToolDefinition(
            name=name,
            func=func,
            description=description,
            parameter_descriptions=parameter_descriptions or {},
            permission_key=permission_key,
        )
        logger.debug("Registered tool: %s", name)

    def execute(self, name: str, args: dict[str, Any] | None = None) -> str:
        """
        Execute a registered tool.

        Args:
            name: Tool name to execute.
            args: Arguments to pass to the tool function.

        Returns:
            Tool result string, or error message.
        """
        args = args or {}

        # Check tool exists
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools.keys()))
            return f"Error: Unknown tool '{name}'. Available tools: {available}"

        # Check permission
        if tool.permission_key and not self._permissions.is_allowed(tool.permission_key):
            return (
                f"Error: Permission denied for tool '{name}'. "
                f"Permission '{tool.permission_key}' is disabled in permissions.json."
            )

        # Execute
        try:
            logger.info("Executing tool: %s(%s)", name, json.dumps(args, default=str))
            result = tool.func(**args)
            logger.info("Tool '%s' completed: %s", name, result[:200] if result else "")
            return result or "Done."
        except TypeError as e:
            # Wrong arguments
            return f"Error: Invalid arguments for tool '{name}': {e}"
        except Exception as e:
            logger.error("Tool '%s' failed: %s", name, e, exc_info=True)
            return f"Error: Tool '{name}' failed — {e}"

    def list_tools(self) -> list[dict[str, Any]]:
        """
        List all registered tools with their descriptions.

        Returns:
            List of dicts with 'name', 'description', and 'parameters'.
        """
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameter_descriptions,
            }
            for t in self._tools.values()
        ]

    def get_tools_prompt(self) -> str:
        """
        Generate a tools description block for the LLM system prompt.

        Returns:
            Formatted string listing all tools and their parameters.
        """
        lines = ["Available tools:"]
        for t in self._tools.values():
            params = ""
            if t.parameter_descriptions:
                param_parts = [
                    f"{k}: {v}" for k, v in t.parameter_descriptions.items()
                ]
                params = f" (parameters: {', '.join(param_parts)})"
            lines.append(f"  - {t.name}: {t.description}{params}")
        return "\n".join(lines)

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools
