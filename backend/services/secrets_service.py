from __future__ import annotations

import logging

from cryptography.fernet import Fernet

from backend.config import settings

logger = logging.getLogger(__name__)


class SecretsService:
    """Encrypts and decrypts sensitive credential strings using Fernet symmetric encryption.

    A single Fernet key is used for the lifetime of the process.  If no key is
    supplied via ``CREDENTIALS_ENCRYPTION_KEY`` a new random key is generated
    and a warning is emitted — this is useful for local development but means
    previously-encrypted values cannot be decrypted after a restart.

    Example::

        svc = SecretsService(key="<base64-fernet-key>")
        token = svc.encrypt("my-secret-token")
        plain = svc.decrypt(token)
    """

    def __init__(self, key: str) -> None:
        if not key:
            generated = Fernet.generate_key()
            logger.warning(
                "CREDENTIALS_ENCRYPTION_KEY is not set. "
                "A temporary key has been generated for this session. "
                "All encrypted values will be unreadable after restart. "
                "Set a stable key in your environment before deploying."
            )
            self._fernet = Fernet(generated)
        else:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt *plaintext* and return the Fernet token as bytes.

        Args:
            plaintext: The secret string to protect.

        Returns:
            Encrypted token bytes suitable for storage in ``LargeBinary`` columns.
        """
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, token: bytes) -> str:
        """Decrypt *token* and return the original plaintext string.

        Args:
            token: The Fernet token bytes previously returned by :meth:`encrypt`.

        Returns:
            The decrypted plaintext string.

        Raises:
            cryptography.fernet.InvalidToken: If the token is invalid or was
                encrypted with a different key.
        """
        return self._fernet.decrypt(token).decode("utf-8")


# Module-level singleton — imported by other modules.
secrets_service = SecretsService(settings.CREDENTIALS_ENCRYPTION_KEY)
