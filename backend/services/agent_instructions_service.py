from __future__ import annotations

"""Service helpers for per-customer agent instructions persistence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_instructions import AgentInstructions
from backend.models.customer import PlatformConnection
from backend.schemas.agent_instructions import AgentInstructionsUpsertPayload


async def get_for_customer(
    db: AsyncSession,
    customer_id: UUID,
) -> AgentInstructions | None:
    """Return the customer's :class:`~backend.models.agent_instructions.AgentInstructions` row.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.

    Returns:
        The ``AgentInstructions`` ORM instance, or ``None`` if no row exists
        for this customer.
    """
    result = await db.execute(
        select(AgentInstructions).where(AgentInstructions.customer_id == customer_id)
    )
    return result.scalar_one_or_none()


async def upsert(
    db: AsyncSession,
    customer_id: UUID,
    payload: AgentInstructionsUpsertPayload,
) -> AgentInstructions:
    """Create or replace the customer's AgentInstructions row.

    Atomically replaces ``content`` and ``enabled``.  If a row already exists
    for *customer_id* it is updated in-place; otherwise a new row is created.
    The operation is idempotent — calling it twice with identical payloads
    produces the same result.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.
        payload: Validated upsert payload containing ``content`` and
            ``enabled``.

    Returns:
        The created or updated ``AgentInstructions`` ORM instance.
    """
    existing = await get_for_customer(db, customer_id)

    if existing is not None:
        existing.content = payload.content
        existing.enabled = payload.enabled
        await db.commit()
        await db.refresh(existing)
        return existing

    row = AgentInstructions(
        customer_id=customer_id,
        content=payload.content,
        enabled=payload.enabled,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def delete(db: AsyncSession, customer_id: UUID) -> bool:
    """Delete the customer's AgentInstructions row.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.

    Returns:
        ``True`` if a row was found and deleted, ``False`` if no row existed.
    """
    row = await get_for_customer(db, customer_id)
    if row is None:
        return False

    await db.delete(row)
    await db.commit()
    return True


async def resolve(db: AsyncSession, connection_id: UUID) -> str | None:
    """Return the effective instructions for a connection.

    Precedence (highest to lowest):

    1. ``PlatformConnection.agent_instructions_override`` — a non-blank string
       stored directly on the connection takes priority.
    2. ``Customer.agent_instructions.content`` — the customer-level default when
       it exists and ``enabled`` is ``True``.
    3. ``None`` — no instructions are available.

    An override that is an empty string or contains only whitespace is treated
    as *not set* and falls through to the customer default.

    **Note:** Whether the *target repository* has its own AGENTS.md is not
    checked here; that probe is the responsibility of the agent runtime
    (Phase 3).

    Args:
        db: Active async database session.
        connection_id: UUID of the ``PlatformConnection`` whose effective
            instructions should be resolved.

    Returns:
        The effective instruction content string, or ``None`` if no
        instructions are configured at any level.
    """
    # Load the connection in one query.
    conn_result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection_id)
    )
    connection = conn_result.scalar_one_or_none()
    if connection is None:
        return None

    # 1. Per-connection override (non-blank wins).
    override = connection.agent_instructions_override
    if override and override.strip():
        return override

    # 2. Customer-level default — load via a second targeted query.
    ai_result = await db.execute(
        select(AgentInstructions).where(AgentInstructions.customer_id == connection.customer_id)
    )
    ai = ai_result.scalar_one_or_none()
    if ai is not None and ai.enabled:
        return ai.content

    return None
