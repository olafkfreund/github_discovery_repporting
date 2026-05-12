from __future__ import annotations

"""Unit tests for agent_instructions_service (direct service layer, no HTTP)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_instructions import AgentInstructions
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import AuthType, Platform
from backend.schemas.agent_instructions import AgentInstructionsUpsertPayload
from backend.services import agent_instructions_service as svc
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer(db: AsyncSession, name: str = "Svc Corp") -> Customer:
    slug = name.lower().replace(" ", "-")
    customer = Customer(name=name, slug=slug)
    db.add(customer)
    await db.flush()
    return customer


async def _create_connection(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    override: str | None = None,
) -> PlatformConnection:
    """Create and persist a minimal PlatformConnection."""
    from json import dumps

    conn = PlatformConnection(
        customer_id=customer_id,
        platform=Platform.github,
        display_name="Test Connection",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(dumps({"token": "test"})),
        org_or_group="test-org",
        agent_instructions_override=override,
    )
    db.add(conn)
    await db.flush()
    return conn


async def _create_ai(
    db: AsyncSession,
    customer_id: uuid.UUID,
    content: str = "Default customer instructions",
    enabled: bool = True,
) -> AgentInstructions:
    row = AgentInstructions(customer_id=customer_id, content=content, enabled=enabled)
    db.add(row)
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# get_for_customer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_for_customer_none(db_session: AsyncSession) -> None:
    """get_for_customer returns None when no row exists."""
    customer = await _create_customer(db_session)
    result = await svc.get_for_customer(db_session, customer.id)
    assert result is None


@pytest.mark.asyncio
async def test_get_for_customer_returns_row(db_session: AsyncSession) -> None:
    """get_for_customer returns the persisted row."""
    customer = await _create_customer(db_session)
    await _create_ai(db_session, customer.id, content="Test content")

    result = await svc.get_for_customer(db_session, customer.id)
    assert result is not None
    assert result.content == "Test content"


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_creates_when_absent(db_session: AsyncSession) -> None:
    """upsert creates a new row when none exists."""
    customer = await _create_customer(db_session)
    payload = AgentInstructionsUpsertPayload(content="New instructions", enabled=True)

    row = await svc.upsert(db_session, customer.id, payload)

    assert row.id is not None
    assert row.customer_id == customer.id
    assert row.content == "New instructions"
    assert row.enabled is True


@pytest.mark.asyncio
async def test_upsert_updates_when_present(db_session: AsyncSession) -> None:
    """upsert replaces content and enabled on an existing row."""
    customer = await _create_customer(db_session)
    original = await _create_ai(db_session, customer.id, content="Original")
    await db_session.commit()

    payload = AgentInstructionsUpsertPayload(content="Replaced", enabled=False)
    updated = await svc.upsert(db_session, customer.id, payload)

    assert updated.id == original.id
    assert updated.content == "Replaced"
    assert updated.enabled is False


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_returns_true(db_session: AsyncSession) -> None:
    """delete returns True when a row exists and is deleted."""
    customer = await _create_customer(db_session)
    await _create_ai(db_session, customer.id)
    await db_session.commit()

    result = await svc.delete(db_session, customer.id)
    assert result is True

    remaining = await svc.get_for_customer(db_session, customer.id)
    assert remaining is None


@pytest.mark.asyncio
async def test_delete_returns_false_when_absent(db_session: AsyncSession) -> None:
    """delete returns False when no row exists."""
    customer = await _create_customer(db_session)
    result = await svc.delete(db_session, customer.id)
    assert result is False


# ---------------------------------------------------------------------------
# resolve — precedence tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_no_override_no_default(db_session: AsyncSession) -> None:
    """resolve returns None when neither override nor customer default exist."""
    customer = await _create_customer(db_session)
    conn = await _create_connection(db_session, customer.id, override=None)
    await db_session.commit()

    result = await svc.resolve(db_session, conn.id)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_customer_default_only(db_session: AsyncSession) -> None:
    """resolve returns customer-level default when no per-connection override is set."""
    customer = await _create_customer(db_session)
    await _create_ai(db_session, customer.id, content="Customer default")
    conn = await _create_connection(db_session, customer.id, override=None)
    await db_session.commit()

    result = await svc.resolve(db_session, conn.id)
    assert result == "Customer default"


@pytest.mark.asyncio
async def test_resolve_override_wins_over_default(db_session: AsyncSession) -> None:
    """resolve returns per-connection override even when customer default exists."""
    customer = await _create_customer(db_session)
    await _create_ai(db_session, customer.id, content="Customer default")
    conn = await _create_connection(db_session, customer.id, override="Connection override")
    await db_session.commit()

    result = await svc.resolve(db_session, conn.id)
    assert result == "Connection override"


@pytest.mark.asyncio
async def test_resolve_empty_string_override_falls_through(db_session: AsyncSession) -> None:
    """resolve treats an empty-string override as not set; falls through to customer default."""
    customer = await _create_customer(db_session)
    await _create_ai(db_session, customer.id, content="Customer default")
    conn = await _create_connection(db_session, customer.id, override="")
    await db_session.commit()

    result = await svc.resolve(db_session, conn.id)
    assert result == "Customer default"


@pytest.mark.asyncio
async def test_resolve_whitespace_only_override_falls_through(db_session: AsyncSession) -> None:
    """resolve treats a whitespace-only override as not set; falls through to customer default."""
    customer = await _create_customer(db_session)
    await _create_ai(db_session, customer.id, content="Customer default")
    conn = await _create_connection(db_session, customer.id, override="   \n\t  ")
    await db_session.commit()

    result = await svc.resolve(db_session, conn.id)
    assert result == "Customer default"


@pytest.mark.asyncio
async def test_resolve_disabled_default_returns_none(db_session: AsyncSession) -> None:
    """resolve returns None when the customer default exists but enabled=False."""
    customer = await _create_customer(db_session)
    await _create_ai(db_session, customer.id, content="Disabled default", enabled=False)
    conn = await _create_connection(db_session, customer.id, override=None)
    await db_session.commit()

    result = await svc.resolve(db_session, conn.id)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_unknown_connection_returns_none(db_session: AsyncSession) -> None:
    """resolve returns None for an unknown connection_id."""
    result = await svc.resolve(db_session, uuid.uuid4())
    assert result is None
