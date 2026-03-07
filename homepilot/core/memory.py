"""
Persistent SQLite memory system for HomePilot.

Stores conversation history, user preferences, and important
events in a local SQLite database. Works alongside the
in-memory ContextMemory used by the real-time voice pipeline.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.memory")


class PersistentMemory:
    """
    SQLite-backed persistent memory for the agent.

    Tables:
        users         — user profile information
        preferences   — key-value user preferences
        conversation_log — full conversation history

    Usage:
        memory = PersistentMemory("memory/database.db")
        memory.log_conversation("hello", "Hi Thomas!")
        history = memory.get_recent_history(limit=5)
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._initialize()

    def _initialize(self) -> None:
        """Create database and tables if they don't exist."""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                last_seen   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS preferences (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER DEFAULT 1,
                key         TEXT NOT NULL UNIQUE,
                value       TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS conversation_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT DEFAULT (datetime('now')),
                role        TEXT NOT NULL,           -- 'user' or 'assistant'
                content     TEXT NOT NULL,
                intent      TEXT DEFAULT '',
                tool_used   TEXT DEFAULT '',
                tool_args   TEXT DEFAULT '',
                tool_result TEXT DEFAULT ''
            );
        """)
        self._conn.commit()
        logger.info("Persistent memory initialized at %s", self._db_path)

    # ── Conversation Logging ─────────────────────────────────

    def log_conversation(
        self,
        user_input: str,
        assistant_response: str,
        intent: str = "",
        tool_used: str = "",
        tool_args: dict[str, Any] | None = None,
        tool_result: str = "",
    ) -> None:
        """Log a full conversation turn (user + assistant)."""
        if not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT INTO conversation_log (role, content, intent, tool_used, tool_args, tool_result) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("user", user_input, intent, "", "", ""),
            )
            self._conn.execute(
                "INSERT INTO conversation_log (role, content, intent, tool_used, tool_args, tool_result) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "assistant", assistant_response, intent,
                    tool_used, json.dumps(tool_args or {}, default=str),
                    tool_result,
                ),
            )
            self._conn.commit()
        except Exception as e:
            logger.error("Failed to log conversation: %s", e)

    def get_recent_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Get recent conversation history.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of dicts with role, content, timestamp, etc.
        """
        if not self._conn:
            return []
        cursor = self._conn.execute(
            "SELECT timestamp, role, content, intent, tool_used "
            "FROM conversation_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_context_for_llm(self, limit: int = 10) -> str:
        """
        Get formatted conversation context for the LLM prompt.

        Args:
            limit: Number of recent exchanges to include.

        Returns:
            Formatted conversation history string.
        """
        history = self.get_recent_history(limit)
        if not history:
            return "No previous conversation history."

        lines = []
        for entry in history:
            role = "User" if entry["role"] == "user" else "Assistant"
            lines.append(f"{role}: {entry['content']}")
        return "\n".join(lines)

    # ── User Preferences ─────────────────────────────────────

    def set_preference(self, key: str, value: str, user_id: int = 1) -> None:
        """Set a user preference (upsert)."""
        if not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT INTO preferences (user_id, key, value, updated_at) "
                "VALUES (?, ?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                (user_id, key, value),
            )
            self._conn.commit()
            logger.debug("Preference set: %s = %s", key, value)
        except Exception as e:
            logger.error("Failed to set preference: %s", e)

    def get_preference(self, key: str, default: str = "") -> str:
        """Get a user preference value."""
        if not self._conn:
            return default
        cursor = self._conn.execute(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row["value"] if row else default

    def get_all_preferences(self) -> dict[str, str]:
        """Get all user preferences as a dict."""
        if not self._conn:
            return {}
        cursor = self._conn.execute("SELECT key, value FROM preferences")
        return {row["key"]: row["value"] for row in cursor.fetchall()}

    # ── User Management ──────────────────────────────────────

    def ensure_user(self, name: str) -> int:
        """Ensure a user exists, return user ID."""
        if not self._conn:
            return 1
        cursor = self._conn.execute(
            "SELECT id FROM users WHERE name = ?", (name,)
        )
        row = cursor.fetchone()
        if row:
            self._conn.execute(
                "UPDATE users SET last_seen = datetime('now') WHERE id = ?",
                (row["id"],),
            )
            self._conn.commit()
            return row["id"]

        cursor = self._conn.execute(
            "INSERT INTO users (name) VALUES (?)", (name,)
        )
        self._conn.commit()
        return cursor.lastrowid or 1

    # ── Statistics ────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        if not self._conn:
            return {}
        stats: dict[str, Any] = {}
        cursor = self._conn.execute(
            "SELECT COUNT(*) as count FROM conversation_log"
        )
        stats["total_conversations"] = cursor.fetchone()["count"]

        cursor = self._conn.execute(
            "SELECT COUNT(*) as count FROM preferences"
        )
        stats["total_preferences"] = cursor.fetchone()["count"]

        cursor = self._conn.execute(
            "SELECT MIN(timestamp) as first, MAX(timestamp) as last "
            "FROM conversation_log"
        )
        row = cursor.fetchone()
        stats["first_conversation"] = row["first"]
        stats["last_conversation"] = row["last"]

        return stats

    # ── Cleanup ───────────────────────────────────────────────

    def trim_history(self, max_entries: int = 1000) -> None:
        """Remove oldest conversation entries beyond the limit."""
        if not self._conn:
            return
        self._conn.execute(
            "DELETE FROM conversation_log WHERE id NOT IN "
            "(SELECT id FROM conversation_log ORDER BY id DESC LIMIT ?)",
            (max_entries,),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Persistent memory closed.")
