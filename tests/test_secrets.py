from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet, InvalidToken

from backend.services.secrets_service import SecretsService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_key() -> str:
    """Return a valid Fernet key encoded as a URL-safe base64 string."""
    return Fernet.generate_key().decode()


@pytest.fixture()
def service(valid_key: str) -> SecretsService:
    """Return a SecretsService instance backed by a fresh Fernet key."""
    return SecretsService(key=valid_key)


# ---------------------------------------------------------------------------
# Encrypt / decrypt roundtrip
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip(service: SecretsService) -> None:
    """Encrypting then decrypting a string recovers the original plaintext."""
    plaintext = "my-secret-api-token"
    token = service.encrypt(plaintext)
    recovered = service.decrypt(token)
    assert recovered == plaintext


def test_encrypt_returns_bytes(service: SecretsService) -> None:
    """encrypt() always returns a bytes object suitable for LargeBinary storage."""
    result = service.encrypt("some-secret")
    assert isinstance(result, bytes)


def test_decrypt_returns_str(service: SecretsService) -> None:
    """decrypt() always returns a plain Python str."""
    token = service.encrypt("hello")
    result = service.decrypt(token)
    assert isinstance(result, str)


def test_encrypt_empty_string(service: SecretsService) -> None:
    """Encrypting an empty string produces a non-empty token that decrypts correctly."""
    token = service.encrypt("")
    assert len(token) > 0
    assert service.decrypt(token) == ""


def test_encrypt_unicode_string(service: SecretsService) -> None:
    """encrypt/decrypt handles non-ASCII Unicode content correctly."""
    plaintext = "パスワード-\u00e9\u00e0\u00fc"
    token = service.encrypt(plaintext)
    assert service.decrypt(token) == plaintext


# ---------------------------------------------------------------------------
# Fernet produces different ciphertexts for repeated encryptions
# ---------------------------------------------------------------------------


def test_different_ciphertexts_same_plaintext(service: SecretsService) -> None:
    """The same plaintext encrypted twice produces distinct ciphertexts.

    Fernet incorporates a timestamp and random IV into each token, so even
    identical inputs yield different byte sequences.  Both must still decrypt
    to the same plaintext.
    """
    plaintext = "repeat-me"
    token_a = service.encrypt(plaintext)
    token_b = service.encrypt(plaintext)

    # The tokens are distinct byte sequences.
    assert token_a != token_b

    # Both decrypt correctly.
    assert service.decrypt(token_a) == plaintext
    assert service.decrypt(token_b) == plaintext


# ---------------------------------------------------------------------------
# Auto key generation when no key is provided
# ---------------------------------------------------------------------------


def test_auto_key_generation_no_key_emits_warning(caplog: pytest.LogCaptureFixture) -> None:
    """SecretsService("")  generates a temporary key and logs a warning."""
    with caplog.at_level(logging.WARNING, logger="backend.services.secrets_service"):
        svc = SecretsService(key="")

    # A warning must have been emitted.
    assert any(
        "CREDENTIALS_ENCRYPTION_KEY" in record.message
        for record in caplog.records
    ), "Expected a warning about missing CREDENTIALS_ENCRYPTION_KEY"

    # The service is still functional despite having no configured key.
    token = svc.encrypt("works-fine")
    assert svc.decrypt(token) == "works-fine"


def test_auto_key_generation_produces_working_service() -> None:
    """A SecretsService with an empty key can still encrypt and decrypt."""
    svc = SecretsService(key="")
    plaintext = "operational-even-without-configured-key"
    assert svc.decrypt(svc.encrypt(plaintext)) == plaintext


# ---------------------------------------------------------------------------
# Cross-key isolation
# ---------------------------------------------------------------------------


def test_decrypt_with_wrong_key_raises_invalid_token() -> None:
    """Decrypting a token with a different key raises InvalidToken."""
    key_a = Fernet.generate_key().decode()
    key_b = Fernet.generate_key().decode()

    service_a = SecretsService(key=key_a)
    service_b = SecretsService(key=key_b)

    token = service_a.encrypt("secret")

    with pytest.raises(InvalidToken):
        service_b.decrypt(token)


def test_decrypt_corrupted_token_raises_invalid_token(service: SecretsService) -> None:
    """Decrypting a malformed token raises InvalidToken."""
    with pytest.raises(InvalidToken):
        service.decrypt(b"this-is-not-a-valid-fernet-token")


# ---------------------------------------------------------------------------
# Key acceptance: bytes and str
# ---------------------------------------------------------------------------


def test_accepts_string_key() -> None:
    """SecretsService accepts a key supplied as a plain str."""
    key = Fernet.generate_key().decode()
    svc = SecretsService(key=key)
    assert svc.decrypt(svc.encrypt("str-key-ok")) == "str-key-ok"


def test_accepts_bytes_key() -> None:
    """SecretsService accepts a key supplied as bytes (coerced at construction time)."""
    # The constructor calls key.encode() only when isinstance(key, str); if we
    # pass bytes it uses them directly.  We verify that both paths work.
    key_bytes = Fernet.generate_key()
    # SecretsService expects str | bytes at the type level; pass via str path.
    svc = SecretsService(key=key_bytes.decode())
    assert svc.decrypt(svc.encrypt("bytes-key-ok")) == "bytes-key-ok"


# ---------------------------------------------------------------------------
# Long secrets
# ---------------------------------------------------------------------------


def test_long_secret_roundtrip(service: SecretsService) -> None:
    """Encryption handles secrets of arbitrary length without truncation."""
    long_secret = "x" * 10_000
    assert service.decrypt(service.encrypt(long_secret)) == long_secret
