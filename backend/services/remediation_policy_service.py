from __future__ import annotations

"""Service helpers for per-customer remediation policy persistence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.remediation_policy import RemediationPolicy
from backend.schemas.remediation_policy import RemediationPolicyUpsert


async def get_for_customer(
    db: AsyncSession,
    customer_id: UUID,
) -> RemediationPolicy | None:
    """Return the customer's :class:`~backend.models.remediation_policy.RemediationPolicy` row.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.

    Returns:
        The ``RemediationPolicy`` ORM instance, or ``None`` if no row exists
        for this customer.
    """
    stmt = select(RemediationPolicy).where(RemediationPolicy.customer_id == customer_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def upsert(
    db: AsyncSession,
    customer_id: UUID,
    payload: RemediationPolicyUpsert,
) -> RemediationPolicy:
    """Create or update the customer's RemediationPolicy.

    Atomically replaces all policy fields.  If a row already exists for
    *customer_id* it is updated in-place; otherwise a new row is created.
    The operation is idempotent — calling it twice with identical payloads
    produces the same result.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.
        payload: Validated upsert payload containing all policy fields.

    Returns:
        The created or updated ``RemediationPolicy`` ORM instance.
    """
    existing = await get_for_customer(db, customer_id)
    if existing is None:
        row = RemediationPolicy(customer_id=customer_id, **payload.model_dump())
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    for field, value in payload.model_dump().items():
        setattr(existing, field, value)
    await db.commit()
    await db.refresh(existing)
    return existing


async def delete(db: AsyncSession, customer_id: UUID) -> bool:
    """Delete the customer's RemediationPolicy row.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.

    Returns:
        ``True`` if a row was found and deleted, ``False`` if no row existed.
    """
    existing = await get_for_customer(db, customer_id)
    if existing is None:
        return False

    await db.delete(existing)
    await db.commit()
    return True
