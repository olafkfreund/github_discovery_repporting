from __future__ import annotations

"""Tests for the LLMConnection SQLAlchemy model."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import Customer
from backend.models.enums import LLMProviderEnum
from backend.models.llm import LLMConnection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, name: str = "Acme Corp") -> Customer:
    """Create and persist a minimal Customer for FK dependencies."""
    slug = name.lower().replace(" ", "-")
    customer = Customer(name=name, slug=slug)
    db.add(customer)
    await db.flush()
    return customer


async def _make_connection(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    name: str = "Primary LLM",
    provider: LLMProviderEnum = LLMProviderEnum.anthropic,
    model: str = "claude-3-5-sonnet-20241022",
    is_default: bool = False,
) -> LLMConnection:
    """Create and persist a minimal LLMConnection."""
    conn = LLMConnection(
        customer_id=customer_id,
        name=name,
        provider=provider,
        model=model,
        is_default=is_default,
    )
    db.add(conn)
    await db.flush()
    return conn


# ---------------------------------------------------------------------------
# Model creation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_connection_create_minimal(db_session: AsyncSession) -> None:
    """LLMConnection persists with all required fields set."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)

    assert conn.id is not None
    assert conn.customer_id == customer.id
    assert conn.name == "Primary LLM"
    assert conn.provider == LLMProviderEnum.anthropic
    assert conn.model == "claude-3-5-sonnet-20241022"
    assert conn.is_default is False
    assert conn.api_key_encrypted is None
    assert conn.extra_config is None
    assert conn.endpoint_url is None


@pytest.mark.asyncio
async def test_llm_connection_create_full(db_session: AsyncSession) -> None:
    """LLMConnection persists with all optional fields set."""
    customer = await _make_customer(db_session)
    conn = LLMConnection(
        customer_id=customer.id,
        name="Full LLM",
        provider=LLMProviderEnum.bedrock,
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        endpoint_url="https://bedrock.us-east-1.amazonaws.com",
        api_key_encrypted=b"encrypted-bytes",
        extra_config={"aws_region": "us-east-1"},
        is_default=True,
    )
    db_session.add(conn)
    await db_session.flush()

    assert conn.endpoint_url == "https://bedrock.us-east-1.amazonaws.com"
    assert conn.api_key_encrypted == b"encrypted-bytes"
    assert conn.extra_config == {"aws_region": "us-east-1"}
    assert conn.is_default is True


# ---------------------------------------------------------------------------
# UniqueConstraint (customer_id, name)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_connection_unique_name_per_customer(db_session: AsyncSession) -> None:
    """Creating two connections with the same name for the same customer raises IntegrityError."""
    customer = await _make_customer(db_session)
    await _make_connection(db_session, customer.id, name="Shared Name")

    duplicate = LLMConnection(
        customer_id=customer.id,
        name="Shared Name",  # same name, same customer
        provider=LLMProviderEnum.openai,
        model="gpt-4o",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_llm_connection_same_name_different_customers(db_session: AsyncSession) -> None:
    """Two connections with the same name but different customers are allowed."""
    customer_a = await _make_customer(db_session, name="Customer A")
    customer_b = await _make_customer(db_session, name="Customer B")

    conn_a = await _make_connection(db_session, customer_a.id, name="Shared Name")
    conn_b = await _make_connection(db_session, customer_b.id, name="Shared Name")

    assert conn_a.id != conn_b.id


# ---------------------------------------------------------------------------
# Cascade delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_connection_cascade_delete(db_session: AsyncSession) -> None:
    """Deleting a Customer removes all of its LLMConnections."""
    customer = await _make_customer(db_session)
    conn_id = (await _make_connection(db_session, customer.id)).id
    await db_session.commit()

    await db_session.delete(customer)
    await db_session.commit()

    result = await db_session.execute(select(LLMConnection).where(LLMConnection.id == conn_id))
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# All provider enum values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_provider_values(db_session: AsyncSession) -> None:
    """Each LLMProviderEnum value can be stored and retrieved."""
    customer = await _make_customer(db_session)

    for provider in LLMProviderEnum:
        conn = LLMConnection(
            customer_id=customer.id,
            name=f"conn-{provider.value}",
            provider=provider,
            model="test-model",
        )
        db_session.add(conn)

    await db_session.flush()

    result = await db_session.execute(
        select(LLMConnection).where(LLMConnection.customer_id == customer.id)
    )
    found_providers = {row.provider for row in result.scalars().all()}
    assert found_providers == set(LLMProviderEnum)
