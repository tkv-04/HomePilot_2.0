"""
Secure logging for HomePilot.

- Filters out secrets and tokens from log output
- Rotating file handler to prevent disk exhaustion
- Configurable log levels
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Patterns that look like secrets — redacted in logs
_SECRET_PATTERNS = [
    re.compile(r'(token["\s:=]+)[^\s,;"]+', re.IGNORECASE),
    re.compile(r'(access_key["\s:=]+)[^\s,;"]+', re.IGNORECASE),
    re.compile(r'(password["\s:=]+)[^\s,;"]+', re.IGNORECASE),
    re.compile(r'(secret["\s:=]+)[^\s,;"]+', re.IGNORECASE),
    re.compile(r'(Bearer\s+)\S+', re.IGNORECASE),
]


class SecretFilter(logging.Filter):
    """Filter that redacts secrets from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in _SECRET_PATTERNS:
                record.msg = pattern.sub(r'\1[REDACTED]', record.msg)
        return True


def setup_logger(
    name: str = "homepilot",
    log_level: str = "INFO",
    log_file: str | None = None,
    max_bytes: int = 5 * 1024 * 1024,   # 5 MB
    backup_count: int = 3,
) -> logging.Logger:
    """
    Configure and return the application logger.

    Args:
        name: Logger name.
        log_level: Logging level string (DEBUG, INFO, WARNING, ERROR).
        log_file: Path to log file. None = stdout only.
        max_bytes: Max log file size before rotation.
        backup_count: Number of rotated backups to keep.

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Prevent duplicate handlers on reload
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    secret_filter = SecretFilter()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(secret_filter)
    logger.addHandler(console)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(secret_filter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "homepilot") -> logging.Logger:
    """Get an existing logger by name."""
    return logging.getLogger(name)
