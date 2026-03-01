"""
Conversation context memory for HomePilot.

Maintains short-term memory of recent interactions
to support multi-turn conversations and follow-up queries.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ConversationTurn:
    """A single conversation turn."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    user_text: str = ""
    intent_name: str = ""
    slots: dict[str, Any] = field(default_factory=dict)
    response: str = ""


class ContextMemory:
    """
    Short-term conversation memory.

    Stores the last N conversation turns to enable:
    - Follow-up references ("do that again", "turn it off too")
    - Context-aware responses
    - Conversation continuity

    Attributes:
        max_turns: Maximum turns to remember.
        turns: Deque of recent ConversationTurn objects.
    """

    def __init__(self, max_turns: int = 10) -> None:
        self.max_turns = max_turns
        self.turns: deque[ConversationTurn] = deque(maxlen=max_turns)

    def add_turn(
        self,
        user_text: str,
        intent_name: str,
        slots: dict[str, Any],
        response: str,
    ) -> None:
        """Record a conversation turn."""
        turn = ConversationTurn(
            user_text=user_text,
            intent_name=intent_name,
            slots=slots,
            response=response,
        )
        self.turns.append(turn)

    @property
    def last_turn(self) -> ConversationTurn | None:
        """Get the most recent turn."""
        return self.turns[-1] if self.turns else None

    @property
    def last_intent(self) -> str:
        """Get the last intent name."""
        return self.turns[-1].intent_name if self.turns else ""

    @property
    def last_device(self) -> str | None:
        """Get the last referenced device from any turn."""
        for turn in reversed(self.turns):
            device = turn.slots.get("device")
            if device:
                return device
        return None

    @property
    def last_room(self) -> str | None:
        """Get the last referenced room."""
        for turn in reversed(self.turns):
            room = turn.slots.get("room")
            if room:
                return room
        return None

    def get_context_summary(self) -> str:
        """Get a summary of recent context for advanced NLU."""
        if not self.turns:
            return "No previous context."

        recent = list(self.turns)[-3:]  # Last 3 turns
        lines = []
        for t in recent:
            lines.append(f"User: {t.user_text} → {t.intent_name}")
        return " | ".join(lines)

    def clear(self) -> None:
        """Clear all conversation memory."""
        self.turns.clear()
