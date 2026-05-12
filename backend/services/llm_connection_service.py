from __future__ import annotations

"""Service helpers for LLM connection persistence and provider construction."""

import time
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.llm.base import LLMMessage, LLMProviderError
from backend.llm.factory import get_llm_provider
from backend.models.llm import LLMConnection
from backend.schemas.llm import (
    LLMConnectionCreate,
    LLMConnectionUpdate,
    LLMConnectionValidateResult,
)
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _encrypt_key(api_key: str | None) -> bytes | None:
    """Encrypt *api_key* with Fernet and return bytes, or ``None``.

    Args:
        api_key: Plaintext API key, or ``None`` when credentials come from
            environment variables or IAM roles.

    Returns:
        Encrypted bytes suitable for ``LargeBinary`` storage, or ``None``.
    """
    if api_key is None:
        return None
    return secrets_service.encrypt(api_key)


async def _clear_other_defaults(db: AsyncSession, customer_id: UUID, exclude_id: UUID | None = None) -> None:
    """Unset ``is_default`` on all LLM connections for *customer_id* except *exclude_id*.

    Args:
        db: Active async database session.
        customer_id: The customer whose connections should be de-defaulted.
        exclude_id: UUID of the connection that should keep its ``is_default``
            flag (the one being set as the new default).
    """
    stmt = (
        update(LLMConnection)
        .where(LLMConnection.customer_id == customer_id)
        .where(LLMConnection.is_default.is_(True))
    )
    if exclude_id is not None:
        stmt = stmt.where(LLMConnection.id != exclude_id)
    await db.execute(stmt.values(is_default=False))


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


async def create_connection(
    db: AsyncSession,
    payload: LLMConnectionCreate,
) -> LLMConnection:
    """Create and persist a new :class:`~backend.models.llm.LLMConnection`.

    When ``payload.is_default`` is ``True``, all other connections for the same
    customer are de-defaulted first so that only one default exists per
    customer at any time.

    Args:
        db: Active async database session.
        payload: Validated creation payload containing plaintext API key.

    Returns:
        The newly created and refreshed ``LLMConnection`` ORM instance.
    """
    extra_dict: dict[str, Any] | None = None
    if payload.extra_config is not None:
        extra_dict = payload.extra_config.model_dump()

    connection = LLMConnection(
        customer_id=payload.customer_id,
        name=payload.name,
        provider=payload.provider,
        model=payload.model,
        endpoint_url=payload.endpoint_url,
        api_key_encrypted=_encrypt_key(payload.api_key),
        extra_config=extra_dict,
        is_default=payload.is_default,
    )
    db.add(connection)
    # Flush to obtain the generated UUID before clearing other defaults.
    await db.flush()

    if payload.is_default:
        await _clear_other_defaults(db, payload.customer_id, exclude_id=connection.id)

    await db.commit()
    await db.refresh(connection)
    return connection


async def list_connections(
    db: AsyncSession,
    customer_id: UUID,
) -> list[LLMConnection]:
    """Return all LLM connections for *customer_id*, ordered by creation time.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.

    Returns:
        List of ``LLMConnection`` ORM instances (may be empty).
    """
    result = await db.execute(
        select(LLMConnection)
        .where(LLMConnection.customer_id == customer_id)
        .order_by(LLMConnection.created_at.desc())
    )
    return list(result.scalars().all())


async def get_connection(
    db: AsyncSession,
    connection_id: UUID,
) -> LLMConnection:
    """Fetch a single LLM connection by primary key or raise HTTP 404.

    Args:
        db: Active async database session.
        connection_id: UUID primary key of the target connection.

    Returns:
        The ``LLMConnection`` ORM instance.

    Raises:
        HTTPException: With status 404 if no connection with *connection_id*
            exists.
    """
    result = await db.execute(
        select(LLMConnection).where(LLMConnection.id == connection_id)
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM connection {connection_id} not found.",
        )
    return connection


async def update_connection(
    db: AsyncSession,
    connection_id: UUID,
    payload: LLMConnectionUpdate,
) -> LLMConnection:
    """Apply a partial update to an existing LLM connection.

    Only fields explicitly provided (non-``None``) in *payload* are written.
    Omitting ``api_key`` does NOT clear the stored encrypted key.  When
    ``is_default`` is set to ``True``, all other connections for the same
    customer are de-defaulted.

    Args:
        db: Active async database session.
        connection_id: UUID of the connection to update.
        payload: Partial update payload.

    Returns:
        The updated and refreshed ``LLMConnection`` ORM instance.

    Raises:
        HTTPException: With status 404 if the connection does not exist.
    """
    connection = await get_connection(db, connection_id)

    if payload.name is not None:
        connection.name = payload.name
    if payload.model is not None:
        connection.model = payload.model
    if payload.endpoint_url is not None:
        connection.endpoint_url = payload.endpoint_url
    if payload.api_key is not None:
        connection.api_key_encrypted = _encrypt_key(payload.api_key)
    if payload.extra_config is not None:
        connection.extra_config = payload.extra_config.model_dump()
    if payload.is_default is not None:
        connection.is_default = payload.is_default
        if payload.is_default:
            await _clear_other_defaults(db, connection.customer_id, exclude_id=connection_id)

    await db.commit()
    await db.refresh(connection)
    return connection


async def delete_connection(
    db: AsyncSession,
    connection_id: UUID,
) -> None:
    """Delete an LLM connection by primary key.

    Args:
        db: Active async database session.
        connection_id: UUID of the connection to remove.

    Raises:
        HTTPException: With status 404 if the connection does not exist.
    """
    connection = await get_connection(db, connection_id)
    await db.delete(connection)
    await db.commit()


# ---------------------------------------------------------------------------
# Provider construction helpers
# ---------------------------------------------------------------------------


def to_provider_config(connection: LLMConnection) -> dict[str, Any]:
    """Build the config dict expected by ``backend.llm.factory.get_llm_provider()``.

    The stored Fernet-encrypted API key is decrypted in memory for the duration
    of the call; it is never written back or logged.

    Args:
        connection: An ``LLMConnection`` ORM instance.

    Returns:
        A plain ``dict`` with keys ``provider``, ``model``, ``api_key``,
        ``endpoint_url``, and ``extra_config``.
    """
    api_key: str | None = None
    if connection.api_key_encrypted is not None:
        api_key = secrets_service.decrypt(connection.api_key_encrypted)

    extra: dict[str, Any] | None = None
    if connection.extra_config is not None:
        extra = dict(connection.extra_config)

    return {
        "provider": connection.provider.value if hasattr(connection.provider, "value") else str(connection.provider),
        "model": connection.model,
        "api_key": api_key,
        "endpoint_url": connection.endpoint_url,
        "extra_config": extra,
    }


async def ping_connection(
    connection: LLMConnection,
) -> LLMConnectionValidateResult:
    """Ping an LLM provider with a minimal request to verify connectivity.

    Constructs a provider instance via the factory, sends a 1-token chat
    request, and returns a :class:`~backend.schemas.llm.LLMConnectionValidateResult`
    with the round-trip latency or error details.

    Args:
        connection: An ``LLMConnection`` ORM instance containing the provider
            credentials and configuration.

    Returns:
        :class:`~backend.schemas.llm.LLMConnectionValidateResult` with
        ``ok=True`` and ``latency_ms`` on success, or ``ok=False`` and an
        ``error`` string on failure.
    """
    config = to_provider_config(connection)
    try:
        provider = get_llm_provider(config)
        start = time.monotonic()
        await provider.chat(
            messages=[LLMMessage(role="user", content="ping")],
            max_tokens=1,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        return LLMConnectionValidateResult(ok=True, latency_ms=latency_ms)
    except LLMProviderError as exc:
        return LLMConnectionValidateResult(ok=False, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return LLMConnectionValidateResult(ok=False, error=f"Unexpected error: {exc}")


async def ping_payload(
    payload_config: dict[str, Any],
) -> LLMConnectionValidateResult:
    """Ping an LLM provider using a raw config dict from a validate payload.

    Used by the ``POST /validate`` endpoint where no persisted connection
    exists.

    Args:
        payload_config: Config dict in the shape expected by
            ``backend.llm.factory.get_llm_provider()``.

    Returns:
        :class:`~backend.schemas.llm.LLMConnectionValidateResult` with
        ``ok=True`` and ``latency_ms`` on success, or ``ok=False`` and an
        ``error`` string on failure.
    """
    try:
        provider = get_llm_provider(payload_config)
        start = time.monotonic()
        await provider.chat(
            messages=[LLMMessage(role="user", content="ping")],
            max_tokens=1,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        return LLMConnectionValidateResult(ok=True, latency_ms=latency_ms)
    except LLMProviderError as exc:
        return LLMConnectionValidateResult(ok=False, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return LLMConnectionValidateResult(ok=False, error=f"Unexpected error: {exc}")
