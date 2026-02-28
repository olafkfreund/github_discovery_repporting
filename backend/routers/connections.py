from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.providers.factory import create_provider
from backend.schemas.customer import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionUpdate,
)
from backend.services import customer_service

router = APIRouter(tags=["connections"])


# ---------------------------------------------------------------------------
# Connection CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/customers/{customer_id}/connections",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a platform connection to a customer",
)
async def add_connection(
    customer_id: UUID,
    payload: ConnectionCreate,
    db: AsyncSession = Depends(get_db),
) -> ConnectionResponse:
    """Register a new platform connection for a customer.

    Plaintext credentials in *payload* are encrypted before persistence and
    are never returned in any response.

    Args:
        customer_id: UUID of the owning customer.
        payload: Connection creation payload including plaintext credentials.
        db: Injected async database session.

    Returns:
        The newly created platform connection record.

    Raises:
        HTTPException: 404 if the customer does not exist.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )
    connection = await customer_service.add_connection(db, customer_id, payload)
    return ConnectionResponse.model_validate(connection)


@router.get(
    "/customers/{customer_id}/connections",
    response_model=list[ConnectionResponse],
    summary="List platform connections for a customer",
)
async def list_connections(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ConnectionResponse]:
    """List all platform connections belonging to a customer.

    Args:
        customer_id: UUID of the owning customer.
        db: Injected async database session.

    Returns:
        A list of connection records, possibly empty.

    Raises:
        HTTPException: 404 if the customer does not exist.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )
    connections = await customer_service.get_connections(db, customer_id)
    return [ConnectionResponse.model_validate(c) for c in connections]


@router.put(
    "/connections/{connection_id}",
    response_model=ConnectionResponse,
    summary="Update a platform connection",
)
async def update_connection(
    connection_id: UUID,
    payload: ConnectionUpdate,
    db: AsyncSession = Depends(get_db),
) -> ConnectionResponse:
    """Apply a partial update to an existing platform connection.

    If ``credentials`` is supplied it will be re-encrypted before persistence.
    All ``None`` fields in *payload* are ignored.

    Args:
        connection_id: UUID of the connection to update.
        payload: Partial update payload.
        db: Injected async database session.

    Returns:
        The updated connection record.

    Raises:
        HTTPException: 404 if no connection with the given ID exists.
    """
    connection = await customer_service.update_connection(db, connection_id, payload)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connection {connection_id} not found.",
        )
    return ConnectionResponse.model_validate(connection)


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a platform connection",
)
async def delete_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a platform connection.

    Args:
        connection_id: UUID of the connection to remove.
        db: Injected async database session.

    Raises:
        HTTPException: 404 if no connection with the given ID exists.
    """
    deleted = await customer_service.delete_connection(db, connection_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connection {connection_id} not found.",
        )


# ---------------------------------------------------------------------------
# Connection validation
# ---------------------------------------------------------------------------


@router.post(
    "/connections/{connection_id}/validate",
    summary="Validate a platform connection's credentials",
)
async def validate_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Validate stored credentials by making a live call to the platform.

    On a successful validation the ``last_validated_at`` timestamp is updated
    on the connection record.  On failure the timestamp is left unchanged and
    the response body describes the problem.

    Args:
        connection_id: UUID of the connection to validate.
        db: Injected async database session.

    Returns:
        A dict with ``"valid"`` (bool) and ``"message"`` (str) keys.

    Raises:
        HTTPException: 404 if no connection with the given ID exists.
    """
    # Fetch the raw ORM instance so the factory can decrypt credentials.
    from sqlalchemy import select

    from backend.models.customer import PlatformConnection

    result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection_id)
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connection {connection_id} not found.",
        )

    try:
        provider = create_provider(connection)
    except NotImplementedError as exc:
        return {
            "valid": False,
            "message": str(exc),
        }
    except ValueError as exc:
        return {
            "valid": False,
            "message": f"Credential configuration error: {exc}",
        }

    try:
        is_valid = await provider.validate_connection()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "401" in msg or "Unauthorized" in msg:
            detail = "Authentication failed — the access token is invalid or expired."
        elif "404" in msg or "Not Found" in msg:
            detail = (
                f"Group or organization '{connection.org_or_group}' not found. "
                "Check the name and ensure the token has access."
            )
        else:
            detail = msg or f"{type(exc).__name__}: {exc!r}"
        return {
            "valid": False,
            "message": detail,
        }

    if is_valid:
        # Stamp the successful validation time.
        connection.last_validated_at = datetime.now(tz=UTC)
        await db.commit()
        await db.refresh(connection)
        return {
            "valid": True,
            "message": "Connection credentials are valid.",
        }

    return {
        "valid": False,
        "message": "Credentials are invalid or the platform is unreachable.",
    }
