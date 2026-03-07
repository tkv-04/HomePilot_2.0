"""
Interactive CLI interface for HomePilot agent.

JARVIS-style interactive terminal with personality,
color-coded output, and smart command handling.
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.core.agent import Agent
    from homepilot.core.memory import PersistentMemory
    from homepilot.core.tool_router import ToolRouter

logger = get_logger("homepilot.cli")

# ANSI color codes
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
_MAGENTA = "\033[95m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


class CLIInterface:
    """
    JARVIS-style interactive command-line interface.

    Features:
    - Color-coded output with typing effect
    - Special commands (/quit, /tools, /memory, /clear, /plan)
    - JARVIS personality in all interactions
    - Sends text to the Agent for smart processing

    Usage:
        cli = CLIInterface(agent, router, memory)
        cli.run()
    """

    def __init__(
        self,
        agent: Agent,
        tool_router: ToolRouter,
        memory: PersistentMemory,
        assistant_name: str = "Jarvis",
        user_name: str = "User",
    ) -> None:
        self._agent = agent
        self._router = tool_router
        self._memory = memory
        self._name = assistant_name
        self._user = user_name

    def run(self) -> None:
        """Start the interactive CLI REPL."""
        self._print_banner()

        # Opening greeting
        greeting = self._agent.process("hello")
        self._speak(greeting)

        while True:
            try:
                user_input = input(
                    f"\n{_CYAN}{_BOLD}{self._user}{_RESET}{_DIM} ➤ {_RESET}"
                ).strip()

                if not user_input:
                    continue

                # Handle special commands
                if user_input.startswith("/"):
                    if not self._handle_special(user_input):
                        break
                    continue

                # Process through agent — show thinking indicator
                self._thinking()
                response = self._agent.process(user_input)
                self._speak(response)

            except KeyboardInterrupt:
                print(f"\n{_DIM}(Ctrl+C — type /quit to exit){_RESET}")
            except EOFError:
                break

        self._print_goodbye()

    def _speak(self, text: str) -> None:
        """Display JARVIS's response with style."""
        print(f"\n  {_GREEN}{_BOLD}{self._name}:{_RESET} {_GREEN}{text}{_RESET}")

    def _thinking(self) -> None:
        """Show a subtle thinking indicator."""
        sys.stdout.write(f"\n  {_DIM}⚡ processing...{_RESET}")
        sys.stdout.flush()
        sys.stdout.write("\r" + " " * 30 + "\r")  # Clear the line

    def _handle_special(self, cmd: str) -> bool:
        """
        Handle /commands. Returns True to continue, False to quit.
        """
        parts = cmd.lower().strip().split(maxsplit=1)
        command = parts[0]

        if command in ("/quit", "/exit", "/q"):
            return False

        elif command == "/tools":
            tools = self._router.list_tools()
            print(f"\n  {_BOLD}⚡ {len(tools)} tools loaded:{_RESET}")
            for t in tools:
                params = ""
                if t["parameters"]:
                    param_list = ", ".join(
                        f"{_DIM}{k}{_RESET}" for k in t["parameters"].keys()
                    )
                    params = f" ({param_list})"
                print(f"    {_CYAN}▸{_RESET} {_BOLD}{t['name']}{_RESET} — {t['description']}{params}")

        elif command == "/memory":
            history = self._memory.get_recent_history(limit=10)
            if not history:
                print(f"\n  {_DIM}No conversation history yet.{_RESET}")
            else:
                print(f"\n  {_BOLD}📝 Recent conversations:{_RESET}")
                for entry in history:
                    if entry["role"] == "user":
                        print(f"    {_CYAN}{self._user}:{_RESET} {entry['content'][:80]}")
                    else:
                        print(f"    {_GREEN}{self._name}:{_RESET} {entry['content'][:80]}")

        elif command == "/stats":
            stats = self._memory.get_stats()
            print(f"\n  {_BOLD}📊 System Stats:{_RESET}")
            for k, v in stats.items():
                label = k.replace("_", " ").title()
                print(f"    {_DIM}▸{_RESET} {label}: {_BOLD}{v}{_RESET}")

        elif command == "/clear":
            self._memory.trim_history(max_entries=0)
            self._speak("Memory wiped. Fresh start.")

        elif command == "/plan":
            request = parts[1] if len(parts) > 1 else ""
            if request:
                self._thinking()
                response = self._agent.process_with_plan(request)
                self._speak(response)
            else:
                print(f"  {_YELLOW}Usage: /plan <complex request>{_RESET}")

        elif command == "/help":
            self._print_help()

        else:
            print(f"  {_YELLOW}Unknown: {cmd}. Type /help for options.{_RESET}")

        return True

    def _print_banner(self) -> None:
        """Print the JARVIS-style startup banner."""
        print(f"""
  {_CYAN}{_BOLD}┌─────────────────────────────────────────────────┐
  │                                                 │
  │   {_GREEN}⚡ {self._name.upper()} — AI AGENT SYSTEM{_CYAN}             │
  │   {_DIM}HomePilot v2.1 • Local AI • No Cloud{_CYAN}{_BOLD}          │
  │                                                 │
  └─────────────────────────────────────────────────┘{_RESET}

  {_DIM}Systems initializing...{_RESET}""")

        # Show system status
        tools = self._router.list_tools()
        status_items = [
            ("LLM Engine", "✅" if self._agent._llm and self._agent._llm.is_available() else "⚠️  offline"),
            ("Tools", f"✅ {len(tools)} loaded"),
            ("Memory", "✅ online"),
            ("Intent Parser", "✅ 4-layer matching"),
        ]
        for label, status in status_items:
            print(f"  {_DIM}  ▸ {label}: {status}{_RESET}")
        print(f"\n  {_DIM}Type naturally or /help for commands.{_RESET}")

    def _print_help(self) -> None:
        """Print help."""
        print(f"""
  {_BOLD}Commands:{_RESET}
    {_CYAN}/tools{_RESET}     — List all available tools
    {_CYAN}/memory{_RESET}    — Show conversation history
    {_CYAN}/stats{_RESET}     — Memory statistics
    {_CYAN}/plan{_RESET} ...  — Multi-step task planning
    {_CYAN}/clear{_RESET}     — Wipe conversation history
    {_CYAN}/quit{_RESET}      — Exit

  {_BOLD}Try saying:{_RESET}
    {_DIM}• check cpu usage
    • open vscode
    • turn on the bedroom light
    • what time is it
    • tell me a joke
    • who are you
    • list files in current directory{_RESET}
""")

    def _print_goodbye(self) -> None:
        """JARVIS-style goodbye."""
        farewell = self._agent.process("goodbye")
        self._speak(farewell)
        print()
