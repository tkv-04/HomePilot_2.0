"""
Encrypted token storage for HomePilot.

Stores API tokens (Home Assistant, etc.) encrypted on disk
using Fernet symmetric encryption from the `cryptography` library.
The master key is derived from a machine-specific seed.
"""

from __future__ import annotations

import os
from pathlib import Path

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.security")


class TokenStore:
    """
    Encrypted token storage.

    Uses Fernet (AES-128-CBC) to encrypt tokens at rest.
    The encryption key is stored in a separate key file
    with restricted permissions.

    Usage:
        store = TokenStore("data/.keyfile")
        store.store_token("ha_token", "my-secret-token")
        token = store.get_token("ha_token")
    """

    def __init__(self, key_file: str = "data/.keyfile") -> None:
        self._key_file = Path(key_file)
        self._token_file = self._key_file.parent / ".tokens.enc"
        self._fernet = None
        self._ensure_key()

    def _ensure_key(self) -> None:
        """Load or generate the encryption key."""
        from cryptography.fernet import Fernet

        self._key_file.parent.mkdir(parents=True, exist_ok=True)

        if self._key_file.exists():
            key = self._key_file.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            self._key_file.write_bytes(key)
            # Restrict permissions (Linux only)
            try:
                os.chmod(self._key_file, 0o600)
            except OSError:
                pass
            logger.info("Generated new encryption key at: %s", self._key_file)

        self._fernet = Fernet(key)

    def store_token(self, name: str, token: str) -> None:
        """
        Encrypt and store a token.

        Args:
            name: Token identifier (e.g., 'ha_token').
            token: Raw token string to encrypt.
        """
        import json

        tokens = self._load_all()
        tokens[name] = self._fernet.encrypt(token.encode("utf-8")).decode("utf-8")
        self._save_all(tokens)
        logger.info("Token '%s' stored (encrypted).", name)

    def get_token(self, name: str) -> str | None:
        """
        Retrieve and decrypt a stored token.

        Args:
            name: Token identifier.

        Returns:
            Decrypted token string, or None if not found.
        """
        tokens = self._load_all()
        encrypted = tokens.get(name)
        if not encrypted:
            return None

        try:
            return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.error("Failed to decrypt token '%s': %s", name, e)
            return None

    def delete_token(self, name: str) -> bool:
        """
        Delete a stored token.

        Args:
            name: Token identifier.

        Returns:
            True if the token was deleted.
        """
        tokens = self._load_all()
        if name in tokens:
            del tokens[name]
            self._save_all(tokens)
            logger.info("Token '%s' deleted.", name)
            return True
        return False

    def list_tokens(self) -> list[str]:
        """List all stored token names (without values)."""
        return list(self._load_all().keys())

    def _load_all(self) -> dict[str, str]:
        """Load all encrypted tokens from disk."""
        import json

        if not self._token_file.exists():
            return {}
        try:
            data = self._token_file.read_text(encoding="utf-8")
            return json.loads(data)
        except Exception as e:
            logger.error("Failed to load token store: %s", e)
            return {}

    def _save_all(self, tokens: dict[str, str]) -> None:
        """Save all encrypted tokens to disk."""
        import json

        try:
            self._token_file.write_text(
                json.dumps(tokens, indent=2),
                encoding="utf-8",
            )
            try:
                os.chmod(self._token_file, 0o600)
            except OSError:
                pass
        except Exception as e:
            logger.error("Failed to save token store: %s", e)
