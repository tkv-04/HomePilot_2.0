"""
Timer and reminder system for HomePilot.

Manages multiple simultaneous timers with persistence,
natural language scheduling, and voice alerts on expiry.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.timers")


@dataclass
class Timer:
    """A single timer instance."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    duration_seconds: float = 0
    message: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str = ""
    is_active: bool = True

    def __post_init__(self) -> None:
        if not self.expires_at and self.duration_seconds > 0:
            expire_time = datetime.now() + timedelta(seconds=self.duration_seconds)
            self.expires_at = expire_time.isoformat()

    @property
    def remaining_seconds(self) -> float:
        """Seconds remaining until expiry."""
        expire = datetime.fromisoformat(self.expires_at)
        remaining = (expire - datetime.now()).total_seconds()
        return max(0.0, remaining)

    @property
    def is_expired(self) -> bool:
        """Whether the timer has expired."""
        return self.remaining_seconds <= 0


class TimerManager:
    """
    Manages multiple concurrent timers with persistence.

    Features:
    - Multiple simultaneous timers
    - Persistent to disk (survives restarts)
    - Voice alerts on completion via callback
    - Background monitoring thread
    - Natural language duration support (via EntityResolver)

    Usage:
        manager = TimerManager(config, on_expire_callback)
        manager.start()
        manager.add_timer(300, "Oven timer", "Check the oven")
        ...
        manager.stop()
    """

    def __init__(
        self,
        persistence_file: str = "data/timers.json",
        max_concurrent: int = 20,
        on_expire: Callable[[Timer], None] | None = None,
    ) -> None:
        self._persistence_path = Path(persistence_file)
        self._max_concurrent = max_concurrent
        self._on_expire = on_expire
        self._timers: dict[str, Timer] = {}
        self._lock = threading.Lock()
        self._monitor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the timer monitoring background thread."""
        self._load_timers()
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="timer-monitor",
        )
        self._monitor_thread.start()
        logger.info("Timer manager started (%d active timers).", len(self._timers))

    def stop(self) -> None:
        """Stop the timer monitoring thread."""
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=3.0)
        self._save_timers()
        logger.info("Timer manager stopped.")

    def add_timer(
        self,
        duration_seconds: float,
        name: str = "",
        message: str = "",
    ) -> str:
        """
        Add a new timer.

        Args:
            duration_seconds: Timer duration in seconds.
            name: Optional timer name.
            message: Optional message to announce on expiry.

        Returns:
            Human-readable confirmation or error message.
        """
        with self._lock:
            active = [t for t in self._timers.values() if t.is_active]
            if len(active) >= self._max_concurrent:
                return f"Maximum of {self._max_concurrent} concurrent timers reached."

            timer = Timer(
                duration_seconds=duration_seconds,
                name=name or f"Timer",
                message=message,
            )
            self._timers[timer.id] = timer
            self._save_timers()

        # Format a friendly duration string
        mins, secs = divmod(int(duration_seconds), 60)
        hours, mins = divmod(mins, 60)
        parts = []
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if mins:
            parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
        if secs and not hours:
            parts.append(f"{secs} second{'s' if secs != 1 else ''}")
        duration_str = " and ".join(parts) or "0 seconds"

        msg = f"Timer set for {duration_str}."
        if message:
            msg += f" I'll remind you to {message}."
        logger.info("Timer added: %s (%.0fs) id=%s", timer.name, duration_seconds, timer.id)
        return msg

    def cancel_timer(self, timer_id: str | None = None) -> str:
        """
        Cancel a timer or all timers.

        Args:
            timer_id: Specific timer ID, or None to cancel all.

        Returns:
            Status message.
        """
        with self._lock:
            if timer_id:
                timer = self._timers.get(timer_id)
                if timer and timer.is_active:
                    timer.is_active = False
                    self._save_timers()
                    return f"Cancelled timer '{timer.name}'."
                return "Timer not found."
            else:
                count = 0
                for t in self._timers.values():
                    if t.is_active:
                        t.is_active = False
                        count += 1
                self._save_timers()
                return f"Cancelled {count} timer{'s' if count != 1 else ''}."

    def list_timers(self) -> str:
        """
        List all active timers.

        Returns:
            Human-readable list of active timers.
        """
        with self._lock:
            active = [t for t in self._timers.values() if t.is_active and not t.is_expired]

        if not active:
            return "No active timers."

        lines = [f"You have {len(active)} active timer{'s' if len(active) != 1 else ''}:"]
        for t in active:
            remaining = t.remaining_seconds
            mins, secs = divmod(int(remaining), 60)
            hours, mins = divmod(mins, 60)
            if hours:
                time_str = f"{hours}h {mins}m remaining"
            elif mins:
                time_str = f"{mins}m {secs}s remaining"
            else:
                time_str = f"{secs}s remaining"
            lines.append(f"  • {t.name}: {time_str}")

        return " ".join(lines)

    def _monitor_loop(self) -> None:
        """Background loop that checks for expired timers."""
        while not self._stop_event.is_set():
            with self._lock:
                for timer in list(self._timers.values()):
                    if timer.is_active and timer.is_expired:
                        timer.is_active = False
                        logger.info("Timer expired: %s (id=%s)", timer.name, timer.id)
                        if self._on_expire:
                            try:
                                self._on_expire(timer)
                            except Exception as e:
                                logger.error("Timer callback error: %s", e)
                self._save_timers()
            time.sleep(1.0)

    def _save_timers(self) -> None:
        """Persist timers to disk."""
        try:
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            data = [asdict(t) for t in self._timers.values() if t.is_active]
            with open(self._persistence_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save timers: %s", e)

    def _load_timers(self) -> None:
        """Load timers from disk."""
        if not self._persistence_path.exists():
            return
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                timer = Timer(**item)
                if timer.is_active and not timer.is_expired:
                    self._timers[timer.id] = timer
            logger.info("Loaded %d persisted timers.", len(self._timers))
        except Exception as e:
            logger.error("Failed to load timers: %s", e)
