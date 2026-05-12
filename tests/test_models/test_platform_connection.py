"""Tests for the PlatformConnection model, specifically the has_write_scope column."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import AuthType, Platform

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_customer() -> Customer:
    """Return an unsaved Customer instance."""
    cid = uuid.uuid4()
    return Customer(
        id=cid,
        name="Test Corp",
        slug=f"test-corp-{cid.hex[:8]}",
    )


def _make_connection(customer_id: uuid.UUID) -> PlatformConnection:
    """Return an unsaved PlatformConnection for the given customer."""
    return PlatformConnection(
        id=uuid.uuid4(),
        customer_id=customer_id,
        platform=Platform.github,
        display_name="Test GitHub",
        auth_type=AuthType.token,
        credentials_encrypted=b"encrypted-placeholder",
        org_or_group="test-org",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_write_scope_defaults_to_none(db_session: AsyncSession) -> None:
    """has_write_scope is NULL on a newly created PlatformConnection row."""
    customer = _make_customer()
    db_session.add(customer)
    await db_session.flush()

    connection = _make_connection(customer.id)
    db_session.add(connection)
    await db_session.flush()

    # Fetch back from DB to confirm the persisted value.
    result = await db_session.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection.id)
    )
    row = result.scalar_one()

    assert row.has_write_scope is None


@pytest.mark.asyncio
async def test_has_write_scope_can_be_set_true(db_session: AsyncSession) -> None:
    """has_write_scope can be persisted as True."""
    customer = _make_customer()
    db_session.add(customer)
    await db_session.flush()

    connection = _make_connection(customer.id)
    connection.has_write_scope = True
    db_session.add(connection)
    await db_session.flush()

    result = await db_session.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection.id)
    )
    row = result.scalar_one()

    assert row.has_write_scope is True


@pytest.mark.asyncio
async def test_has_write_scope_can_be_set_false(db_session: AsyncSession) -> None:
    """has_write_scope can be persisted as False."""
    customer = _make_customer()
    db_session.add(customer)
    await db_session.flush()

    connection = _make_connection(customer.id)
    connection.has_write_scope = False
    db_session.add(connection)
    await db_session.flush()

    result = await db_session.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection.id)
    )
    row = result.scalar_one()

    assert row.has_write_scope is False


@pytest.mark.asyncio
async def test_has_write_scope_can_be_updated(db_session: AsyncSession) -> None:
    """has_write_scope can transition from None → True → False."""
    customer = _make_customer()
    db_session.add(customer)
    await db_session.flush()

    connection = _make_connection(customer.id)
    db_session.add(connection)
    await db_session.flush()

    # Initially None
    assert connection.has_write_scope is None

    # Set to True
    connection.has_write_scope = True
    await db_session.flush()
    assert connection.has_write_scope is True

    # Update to False
    connection.has_write_scope = False
    await db_session.flush()
    assert connection.has_write_scope is False
