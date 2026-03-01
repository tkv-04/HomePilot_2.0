"""
Security validator for HomePilot.

Validates all commands before execution:
- Whitelist enforcement
- Input sanitization
- Rate limiting
- Injection prevention
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING

from homepilot.utils.logger import get_logger

if TYPE_CHECKING:
    from homepilot.config.settings import SecurityConfig

logger = get_logger("homepilot.security")

# Characters that should NEVER appear in commands
_DANGEROUS_CHARS = re.compile(r"[;&|`$\(\)\{\}<>\\]")

# Shell injection patterns
_INJECTION_PATTERNS = [
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\bchmod\b", re.IGNORECASE),
    re.compile(r"\bchown\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bformat\b", re.IGNORECASE),
    re.compile(r"\bcurl\b", re.IGNORECASE),
    re.compile(r"\bwget\b", re.IGNORECASE),
    re.compile(r"\bnc\b", re.IGNORECASE),
    re.compile(r"\bpython\s+-c\b", re.IGNORECASE),
    re.compile(r"\beval\b", re.IGNORECASE),
    re.compile(r"\bexec\b", re.IGNORECASE),
]


class SecurityValidator:
    """
    Command security validator.

    Validates all commands against whitelists, sanitizes
    inputs, and enforces rate limiting. Every command must
    pass validation before execution.
    """

    def __init__(self, config: SecurityConfig) -> None:
        self._config = config
        self._rate_tracker: dict[str, list[float]] = defaultdict(list)

    def validate_command(
        self,
        command_type: str,
        parameters: dict | None = None,
    ) -> tuple[bool, str]:
        """
        Validate a command before execution.

        Args:
            command_type: Type of command (e.g., 'launch_app', 'volume', 'shutdown').
            parameters: Command parameters to validate.

        Returns:
            Tuple of (is_valid, reason).
        """
        if not self._config.enable_command_validation:
            return True, "Validation disabled"

        parameters = parameters or {}

        # Rate limiting
        if self._config.enable_rate_limiting:
            ok, reason = self._check_rate_limit(command_type)
            if not ok:
                return False, reason

        # Sanitize all string parameters
        for key, value in parameters.items():
            if isinstance(value, str):
                ok, reason = self._sanitize_input(value)
                if not ok:
                    logger.warning(
                        "Input validation failed for %s.%s: %s",
                        command_type, key, reason,
                    )
                    return False, reason

        return True, "OK"

    def validate_app_name(self, app_name: str, allowed_apps: set[str]) -> tuple[bool, str]:
        """
        Validate an application name against the whitelist.

        Args:
            app_name: Application name to validate.
            allowed_apps: Set of whitelisted application names.

        Returns:
            Tuple of (is_valid, reason).
        """
        clean = app_name.strip().lower()

        # Check for dangerous characters
        if _DANGEROUS_CHARS.search(clean):
            return False, "Application name contains invalid characters."

        # Check whitelist
        if clean not in allowed_apps:
            return False, f"Application '{clean}' is not whitelisted."

        return True, "OK"

    def _sanitize_input(self, value: str) -> tuple[bool, str]:
        """
        Sanitize a string input.

        Checks for shell injection attempts and dangerous patterns.
        """
        if not value:
            return True, "OK"

        # Check for dangerous characters
        if _DANGEROUS_CHARS.search(value):
            return False, f"Input contains dangerous characters: '{value}'"

        # Check for injection patterns
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(value):
                return False, f"Input matches dangerous pattern: '{value}'"

        # Length limit
        if len(value) > 500:
            return False, "Input exceeds maximum length."

        return True, "OK"

    def _check_rate_limit(self, command_type: str) -> tuple[bool, str]:
        """
        Check rate limiting for a command type.

        Returns:
            Tuple of (is_allowed, reason).
        """
        now = time.monotonic()
        window = 60.0  # 1 minute window
        max_rate = self._config.rate_limit_per_minute

        # Clean old entries
        timestamps = self._rate_tracker[command_type]
        self._rate_tracker[command_type] = [
            t for t in timestamps if now - t < window
        ]

        if len(self._rate_tracker[command_type]) >= max_rate:
            logger.warning(
                "Rate limit exceeded for command type '%s' (%d/%d per minute)",
                command_type, len(self._rate_tracker[command_type]), max_rate,
            )
            return False, f"Rate limit exceeded. Maximum {max_rate} commands per minute."

        self._rate_tracker[command_type].append(now)
        return True, "OK"
