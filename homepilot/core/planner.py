"""
Multi-step task planner for HomePilot agent.

Breaks complex user requests into sequential steps,
each mapped to a registered tool. The agent executes
steps one by one, feeding results forward.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.planner")


@dataclass
class PlanStep:
    """A single step in a multi-step plan."""
    step_number: int
    description: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    status: str = "pending"  # pending | running | done | failed


@dataclass
class Plan:
    """A complete execution plan."""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    status: str = "pending"  # pending | running | done | failed

    @property
    def is_complete(self) -> bool:
        return all(s.status in ("done", "failed") for s in self.steps)

    @property
    def summary(self) -> str:
        lines = [f"Plan: {self.goal}"]
        for s in self.steps:
            icon = {"pending": "⏳", "running": "🔄", "done": "✅", "failed": "❌"}.get(s.status, "?")
            lines.append(f"  {icon} Step {s.step_number}: {s.description} [{s.tool}]")
            if s.result:
                lines.append(f"       → {s.result[:100]}")
        return "\n".join(lines)


class Planner:
    """
    LLM-powered task decomposition planner.

    Takes a complex user request and asks the LLM to
    break it into ordered steps, each mapped to a tool.

    Usage:
        planner = Planner(llm_func, available_tools)
        plan = planner.create_plan("Deploy my project")
        # plan.steps = [{tool: "git_pull", ...}, {tool: "run_python_script", ...}]
    """

    PLAN_PROMPT = """You are a task planner. Break the user's request into sequential steps.

Each step must use exactly one of these available tools:
{tools}

Respond ONLY with a JSON array of steps. Each step has:
- "step": step number (integer)
- "description": what this step does (string)
- "tool": tool name from the list above (string)
- "args": arguments as a JSON object (object)

Example response:
[
  {{"step": 1, "description": "Pull latest code from repository", "tool": "git_pull", "args": {{}}}},
  {{"step": 2, "description": "Check repository status", "tool": "git_status", "args": {{}}}}
]

If the request is simple and only needs one step, return a single-element array.
If the request cannot be accomplished with the available tools, return an empty array [].

User's request: {request}"""

    def __init__(
        self,
        llm_generate: Any = None,
        max_steps: int = 10,
    ) -> None:
        """
        Args:
            llm_generate: Callable that takes a prompt string and returns
                          an LLM response string. If None, a simple
                          single-step fallback is used.
            max_steps: Maximum allowed steps in a plan.
        """
        self._llm_generate = llm_generate
        self._max_steps = max_steps

    def create_plan(
        self,
        request: str,
        available_tools: list[dict[str, Any]],
    ) -> Plan | None:
        """
        Create an execution plan for a complex request.

        Args:
            request: The user's complex request.
            available_tools: List of tool definitions from ToolRouter.

        Returns:
            A Plan object with ordered steps, or None if planning fails.
        """
        if not self._llm_generate:
            logger.info("No LLM available for planning — skipping")
            return None

        # Format tools for the prompt
        tool_lines = []
        for t in available_tools:
            params = ""
            if t.get("parameters"):
                params = f" (params: {json.dumps(t['parameters'])})"
            tool_lines.append(f"  - {t['name']}: {t['description']}{params}")
        tools_str = "\n".join(tool_lines)

        prompt = self.PLAN_PROMPT.format(tools=tools_str, request=request)

        try:
            response = self._llm_generate(prompt)
            if not response:
                return None

            steps_data = self._parse_plan_response(response)
            if not steps_data:
                return None

            plan = Plan(goal=request)
            for s in steps_data[: self._max_steps]:
                plan.steps.append(PlanStep(
                    step_number=s.get("step", len(plan.steps) + 1),
                    description=s.get("description", ""),
                    tool=s.get("tool", ""),
                    args=s.get("args", {}),
                ))

            logger.info(
                "Created plan with %d steps for: %s",
                len(plan.steps), request,
            )
            return plan

        except Exception as e:
            logger.error("Planning failed: %s", e, exc_info=True)
            return None

    def _parse_plan_response(self, response: str) -> list[dict[str, Any]]:
        """Extract a JSON array of steps from the LLM response."""
        # Try to find JSON array in the response
        # The LLM may wrap it in markdown code blocks
        text = response.strip()

        # Remove markdown code fences
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)

        # Find the JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Try parsing the entire response
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        logger.warning("Could not parse plan response: %s", text[:200])
        return []
