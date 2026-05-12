from __future__ import annotations

"""CRUD and validation router for per-customer LLM provider connections."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.llm import (
    LLMConnectionCreate,
    LLMConnectionRead,
    LLMConnectionUpdate,
    LLMConnectionValidatePayload,
    LLMConnectionValidateResult,
)
from backend.services import customer_service
from backend.services import llm_connection_service as svc

router = APIRouter(prefix="/api/llm-connections", tags=["llm-connections"])

# ---------------------------------------------------------------------------
# LLM connection CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=list[LLMConnectionRead],
    summary="List LLM connections for a customer",
)
async def list_connections(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[LLMConnectionRead]:
    """Return all LLM connections belonging to *customer_id*.

    Args:
        customer_id: Query parameter; UUID of the owning customer.
        db: Injected async database session.

    Returns:
        List of serialised ``LLMConnectionRead`` records (may be empty).

    Raises:
        HTTPException: 404 when the customer does not exist.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Customer {customer_id} not found.")

    connections = await svc.list_connections(db, customer_id)
    return [LLMConnectionRead.model_validate(c) for c in connections]


@router.post(
    "/",
    response_model=LLMConnectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new LLM connection",
)
async def create_connection(
    payload: LLMConnectionCreate,
    db: AsyncSession = Depends(get_db),
) -> LLMConnectionRead:
    """Create and persist a new LLM connection for a customer.

    # TODO: gate behind require_role("customer_admin")

    The plaintext ``api_key`` is encrypted before persistence and is never
    returned in the response.

    Args:
        payload: Validated creation payload.
        db: Injected async database session.

    Returns:
        Serialised ``LLMConnectionRead`` of the newly created record.

    Raises:
        HTTPException: 404 when the owning customer does not exist.
        HTTPException: 409 when a connection with the same name already exists
            for this customer.
    """
    customer = await customer_service.get_customer(db, payload.customer_id)
    if customer is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Customer {payload.customer_id} not found.",
        )

    try:
        connection = await svc.create_connection(db, payload)
    except Exception as exc:
        # Surface unique constraint violations as a 409 response.
        exc_str = str(exc).lower()
        if "unique" in exc_str or "duplicate" in exc_str:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"An LLM connection named '{payload.name}' already exists for this customer.",
            ) from exc
        raise

    return LLMConnectionRead.model_validate(connection)


@router.get(
    "/{connection_id}",
    response_model=LLMConnectionRead,
    summary="Get a single LLM connection",
)
async def get_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> LLMConnectionRead:
    """Retrieve a single LLM connection by UUID.

    Args:
        connection_id: UUID path parameter.
        db: Injected async database session.

    Returns:
        Serialised ``LLMConnectionRead``.

    Raises:
        HTTPException: 404 when no connection with *connection_id* exists.
    """
    connection = await svc.get_connection(db, connection_id)
    return LLMConnectionRead.model_validate(connection)


@router.put(
    "/{connection_id}",
    response_model=LLMConnectionRead,
    summary="Update an LLM connection",
)
async def update_connection(
    connection_id: UUID,
    payload: LLMConnectionUpdate,
    db: AsyncSession = Depends(get_db),
) -> LLMConnectionRead:
    """Apply a partial update to an LLM connection.

    # TODO: gate behind require_role("customer_admin")

    Omitting ``api_key`` does NOT clear the stored encrypted key.

    Args:
        connection_id: UUID path parameter.
        payload: Partial update payload.
        db: Injected async database session.

    Returns:
        Serialised ``LLMConnectionRead`` with the applied changes.

    Raises:
        HTTPException: 404 when no connection with *connection_id* exists.
    """
    connection = await svc.update_connection(db, connection_id, payload)
    return LLMConnectionRead.model_validate(connection)


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an LLM connection",
)
async def delete_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an LLM connection by UUID.

    # TODO: gate behind require_role("customer_admin")

    Args:
        connection_id: UUID path parameter.
        db: Injected async database session.

    Raises:
        HTTPException: 404 when no connection with *connection_id* exists.
    """
    await svc.delete_connection(db, connection_id)


# ---------------------------------------------------------------------------
# Validate / test endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/validate",
    response_model=LLMConnectionValidateResult,
    summary="Validate an LLM provider configuration without persisting it",
)
async def validate_connection(
    payload: LLMConnectionValidatePayload,
) -> LLMConnectionValidateResult:
    """Test an LLM provider configuration without creating a database record.

    # TODO: gate behind require_role("customer_admin")

    Builds an ephemeral provider instance from the payload and issues a
    1-token ping to verify connectivity and credentials.

    Args:
        payload: Connection details to test (not persisted).

    Returns:
        :class:`~backend.schemas.llm.LLMConnectionValidateResult` with
        ``ok=True`` and ``latency_ms`` on success, or ``ok=False`` and an
        ``error`` string on failure.
    """
    extra_dict: dict[str, Any] | None = None
    if payload.extra_config is not None:
        extra_dict = payload.extra_config.model_dump()

    config = {
        "provider": payload.provider.value,
        "model": payload.model,
        "api_key": payload.api_key,
        "endpoint_url": payload.endpoint_url,
        "extra_config": extra_dict,
    }
    return await svc.ping_payload(config)


@router.post(
    "/{connection_id}/test",
    response_model=LLMConnectionValidateResult,
    summary="Test a persisted LLM connection",
)
async def test_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> LLMConnectionValidateResult:
    """Test a persisted LLM connection by issuing a 1-token ping.

    # TODO: gate behind require_role("customer_admin")

    Args:
        connection_id: UUID of the connection to test.
        db: Injected async database session.

    Returns:
        :class:`~backend.schemas.llm.LLMConnectionValidateResult` with
        ``ok=True`` and ``latency_ms`` on success, or ``ok=False`` and an
        ``error`` string on failure.

    Raises:
        HTTPException: 404 when no connection with *connection_id* exists.
    """
    connection = await svc.get_connection(db, connection_id)
    return await svc.ping_connection(connection)
