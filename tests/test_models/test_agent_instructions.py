from __future__ import annotations

"""Tests for the AgentInstructions SQLAlchemy model."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_instructions import AgentInstructions
from backend.models.customer import Customer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, name: str = "Test Corp") -> Customer:
    """Create and persist a minimal Customer for FK dependencies."""
    slug = name.lower().replace(" ", "-")
    customer = Customer(name=name, slug=slug)
    db.add(customer)
    await db.flush()
    return customer


async def _make_ai(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    content: str = "# Default Instructions\n\nPlease follow our coding standards.",
    enabled: bool = True,
) -> AgentInstructions:
    """Create and persist a minimal AgentInstructions row."""
    row = AgentInstructions(
        customer_id=customer_id,
        content=content,
        enabled=enabled,
    )
    db.add(row)
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# Model creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_instructions_create_minimal(db_session: AsyncSession) -> None:
    """AgentInstructions persists with all required fields."""
    customer = await _make_customer(db_session)
    row = await _make_ai(db_session, customer.id)

    assert row.id is not None
    assert row.customer_id == customer.id
    assert row.content == "# Default Instructions\n\nPlease follow our coding standards."
    assert row.enabled is True


@pytest.mark.asyncio
async def test_agent_instructions_disabled(db_session: AsyncSession) -> None:
    """AgentInstructions can be stored with enabled=False."""
    customer = await _make_customer(db_session)
    row = await _make_ai(db_session, customer.id, enabled=False)

    assert row.enabled is False


# ---------------------------------------------------------------------------
# UniqueConstraint on customer_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_instructions_unique_per_customer(db_session: AsyncSession) -> None:
    """Creating two AgentInstructions rows for the same customer raises IntegrityError."""
    customer = await _make_customer(db_session)
    await _make_ai(db_session, customer.id, content="First")

    duplicate = AgentInstructions(
        customer_id=customer.id,
        content="Second",
        enabled=True,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_agent_instructions_different_customers_allowed(db_session: AsyncSession) -> None:
    """Two AgentInstructions rows with different customers are allowed."""
    customer_a = await _make_customer(db_session, name="Customer A")
    customer_b = await _make_customer(db_session, name="Customer B")

    row_a = await _make_ai(db_session, customer_a.id, content="Instructions A")
    row_b = await _make_ai(db_session, customer_b.id, content="Instructions B")

    assert row_a.id != row_b.id
    assert row_a.customer_id != row_b.customer_id


# ---------------------------------------------------------------------------
# Cascade delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_instructions_cascade_delete(db_session: AsyncSession) -> None:
    """Deleting a Customer removes its AgentInstructions row."""
    customer = await _make_customer(db_session)
    row_id = (await _make_ai(db_session, customer.id)).id
    await db_session.commit()

    await db_session.delete(customer)
    await db_session.commit()

    result = await db_session.execute(
        select(AgentInstructions).where(AgentInstructions.id == row_id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Bidirectional relationship
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_instructions_customer_relationship(db_session: AsyncSession) -> None:
    """AgentInstructions.customer_id correctly references the owning Customer."""
    customer = await _make_customer(db_session)
    row = await _make_ai(db_session, customer.id, content="Relationship check")
    await db_session.commit()

    # Reload the AgentInstructions row from DB and verify it points to the right customer.
    result = await db_session.execute(
        select(AgentInstructions).where(AgentInstructions.customer_id == customer.id)
    )
    ai = result.scalar_one_or_none()

    assert ai is not None
    assert ai.id == row.id
    assert ai.customer_id == customer.id
    assert ai.content == "Relationship check"
