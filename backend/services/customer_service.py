from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import Customer, PlatformConnection
from backend.schemas.customer import (
    ConnectionCreate,
    ConnectionUpdate,
    CustomerCreate,
    CustomerUpdate,
)
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert a customer name to a URL-safe slug.

    Converts to lowercase, replaces whitespace runs with a single hyphen, then
    strips any character that is not alphanumeric or a hyphen.

    Example::

        >>> _slugify("Acme Corp.")
        'acme-corp'
    """
    lowered = name.lower()
    hyphenated = re.sub(r"\s+", "-", lowered)
    slug = re.sub(r"[^a-z0-9\-]", "", hyphenated)
    # Collapse consecutive hyphens introduced by stripping non-alphanumeric chars.
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Customer CRUD
# ---------------------------------------------------------------------------


async def create_customer(db: AsyncSession, data: CustomerCreate) -> Customer:
    """Create and persist a new :class:`~backend.models.customer.Customer`.

    The ``slug`` field is derived automatically from ``data.name``.

    Args:
        db: An active async database session.
        data: Validated creation payload.

    Returns:
        The newly created and refreshed ``Customer`` ORM instance.
    """
    customer = Customer(
        name=data.name,
        slug=_slugify(data.name),
        contact_email=data.contact_email,
        notes=data.notes,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


async def get_customers(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[Customer]:
    """Return a paginated list of customers ordered alphabetically by name.

    Args:
        db: An active async database session.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.

    Returns:
        A list of ``Customer`` ORM instances, possibly empty.
    """
    result = await db.execute(
        select(Customer).order_by(Customer.name).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_customer(db: AsyncSession, customer_id: UUID) -> Customer | None:
    """Fetch a single customer by primary key.

    Args:
        db: An active async database session.
        customer_id: The UUID primary key of the target customer.

    Returns:
        The ``Customer`` ORM instance, or ``None`` if not found.
    """
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    return result.scalar_one_or_none()


async def update_customer(
    db: AsyncSession,
    customer_id: UUID,
    data: CustomerUpdate,
) -> Customer | None:
    """Apply a partial update to an existing customer.

    Only fields explicitly set in *data* (i.e. not ``None``) are written.
    When ``name`` changes the ``slug`` is regenerated automatically.

    Args:
        db: An active async database session.
        customer_id: The UUID of the customer to update.
        data: Partial update payload; ``None`` values are ignored.

    Returns:
        The updated ``Customer`` instance, or ``None`` if not found.
    """
    customer = await get_customer(db, customer_id)
    if customer is None:
        return None

    update_data = data.model_dump(exclude_none=True)
    if "name" in update_data:
        update_data["slug"] = _slugify(update_data["name"])

    for field, value in update_data.items():
        setattr(customer, field, value)

    await db.commit()
    await db.refresh(customer)
    return customer


async def delete_customer(db: AsyncSession, customer_id: UUID) -> bool:
    """Delete a customer and all cascading records.

    Args:
        db: An active async database session.
        customer_id: The UUID of the customer to remove.

    Returns:
        ``True`` if the customer was found and deleted, ``False`` otherwise.
    """
    customer = await get_customer(db, customer_id)
    if customer is None:
        return False

    await db.delete(customer)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# PlatformConnection CRUD
# ---------------------------------------------------------------------------


async def add_connection(
    db: AsyncSession,
    customer_id: UUID,
    data: ConnectionCreate,
) -> PlatformConnection:
    """Register a new platform connection for a customer.

    The plaintext ``credentials`` field in *data* is encrypted before
    persistence; only the encrypted bytes are stored.

    Args:
        db: An active async database session.
        customer_id: The UUID of the owning customer.
        data: Validated connection creation payload containing plaintext creds.

    Returns:
        The newly created and refreshed ``PlatformConnection`` ORM instance.
    """
    encrypted = secrets_service.encrypt(data.credentials)
    connection = PlatformConnection(
        customer_id=customer_id,
        platform=data.platform,
        display_name=data.display_name,
        base_url=data.base_url,
        auth_type=data.auth_type,
        credentials_encrypted=encrypted,
        org_or_group=data.org_or_group,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    return connection


async def get_connections(
    db: AsyncSession,
    customer_id: UUID,
) -> list[PlatformConnection]:
    """List all platform connections belonging to a customer.

    Args:
        db: An active async database session.
        customer_id: The UUID of the owning customer.

    Returns:
        A list of ``PlatformConnection`` ORM instances, possibly empty.
    """
    result = await db.execute(
        select(PlatformConnection).where(
            PlatformConnection.customer_id == customer_id
        )
    )
    return list(result.scalars().all())


async def update_connection(
    db: AsyncSession,
    connection_id: UUID,
    data: ConnectionUpdate,
) -> PlatformConnection | None:
    """Apply a partial update to an existing platform connection.

    If ``credentials`` is supplied it is re-encrypted before persistence.
    All other ``None`` fields in *data* are skipped.

    Args:
        db: An active async database session.
        connection_id: The UUID of the connection to update.
        data: Partial update payload; ``None`` values are ignored.

    Returns:
        The updated ``PlatformConnection`` instance, or ``None`` if not found.
    """
    result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection_id)
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        return None

    update_data = data.model_dump(exclude_none=True)

    # Re-encrypt credentials if new plaintext was provided.
    if "credentials" in update_data:
        update_data["credentials_encrypted"] = secrets_service.encrypt(
            update_data.pop("credentials")
        )

    for field, value in update_data.items():
        setattr(connection, field, value)

    await db.commit()
    await db.refresh(connection)
    return connection


async def delete_connection(db: AsyncSession, connection_id: UUID) -> bool:
    """Delete a platform connection.

    Args:
        db: An active async database session.
        connection_id: The UUID of the connection to remove.

    Returns:
        ``True`` if the connection was found and deleted, ``False`` otherwise.
    """
    result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection_id)
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        return False

    await db.delete(connection)
    await db.commit()
    return True
