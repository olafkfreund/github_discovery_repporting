from __future__ import annotations

"""Tests for GET /api/customers/{id}/cost-status."""

import secrets
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import AuthType, LLMProviderEnum, Platform, ScanStatus
from backend.models.llm import LLMConnection
from backend.models.remediation_policy import RemediationPolicy
from backend.models.scan import Scan
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer_via_api(client: AsyncClient, name: str = "CostStatus Corp") -> dict:
    resp = await client.post(
        "/api/customers/",
        json={"name": name, "contact_email": "cost@example.com"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _seed_run(
    db: AsyncSession,
    customer: Customer,
    cost_usd: float,
    *,
    created_at: datetime | None = None,
) -> AgentRun:
    """Insert a minimal AgentRun row linked to *customer* via a fresh scan."""
    import json

    conn = PlatformConnection(
        customer_id=customer.id,
        platform=Platform.github,
        display_name="Seed GH",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(json.dumps({"token": "ghp_seed"})),
        org_or_group="seed-org",
        is_active=True,
    )
    db.add(conn)
    await db.flush()

    scan = Scan(
        customer_id=customer.id,
        connection_id=conn.id,
        status=ScanStatus.completed,
    )
    db.add(scan)
    await db.flush()

    llm = LLMConnection(
        customer_id=customer.id,
        name=f"llm-{uuid.uuid4().hex[:6]}",
        provider=LLMProviderEnum.anthropic,
        model="claude-sonnet-4-6",
        is_default=True,
    )
    db.add(llm)
    await db.flush()

    run = AgentRun(
        scan_id=scan.id,
        llm_connection_id=llm.id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        status="completed",
        runtime_mode="backend",
        callback_secret=secrets.token_bytes(32),
        total_cost_usd=cost_usd,
    )
    db.add(run)
    await db.flush()

    if created_at is not None:
        await db.execute(
            update(AgentRun).where(AgentRun.id == run.id).values(created_at=created_at)
        )
        await db.flush()
        await db.refresh(run)

    await db.commit()
    return run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_status_empty_customer_defaults(client: AsyncClient) -> None:
    """Empty customer returns 200 with spent=0, cap=100, exceeded=False."""
    customer = await _create_customer_via_api(client)
    resp = await client.get(f"/api/customers/{customer['id']}/cost-status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["customer_id"] == customer["id"]
    assert data["spent_usd"] == pytest.approx(0.0)
    assert data["cap_usd"] == pytest.approx(100.0)
    assert data["remaining_usd"] == pytest.approx(100.0)
    assert data["exceeded"] is False
    assert "month_start" in data


@pytest.mark.asyncio
async def test_cost_status_unknown_customer_200_defaults(client: AsyncClient) -> None:
    """Unknown customer UUID returns 200 (idempotent aggregate — no 404)."""
    unknown_id = str(uuid.uuid4())
    resp = await client.get(f"/api/customers/{unknown_id}/cost-status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["spent_usd"] == pytest.approx(0.0)
    assert data["cap_usd"] == pytest.approx(100.0)
    assert data["exceeded"] is False


@pytest.mark.asyncio
async def test_cost_status_reflects_seeded_runs(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Endpoint reflects actual AgentRun costs seeded in the database."""
    customer_data = await _create_customer_via_api(client)
    customer_id = uuid.UUID(customer_data["id"])

    # Load the ORM customer so we can pass it to _seed_run.
    from sqlalchemy import select

    from backend.models.customer import Customer

    customer_row = (
        await db_session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one()

    await _seed_run(db_session, customer_row, cost_usd=7.50)
    await _seed_run(db_session, customer_row, cost_usd=2.50)
    # db_session already committed inside _seed_run.

    resp = await client.get(f"/api/customers/{customer_data['id']}/cost-status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["spent_usd"] == pytest.approx(10.0)
    assert data["remaining_usd"] == pytest.approx(90.0)
    assert data["exceeded"] is False


@pytest.mark.asyncio
async def test_cost_status_reflects_policy_cap(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Endpoint reports the cap from RemediationPolicy when one exists."""
    customer_data = await _create_customer_via_api(client)
    customer_id = uuid.UUID(customer_data["id"])

    policy = RemediationPolicy(
        customer_id=customer_id,
        max_cost_usd_per_month=42.0,
    )
    db_session.add(policy)
    await db_session.commit()

    resp = await client.get(f"/api/customers/{customer_data['id']}/cost-status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cap_usd"] == pytest.approx(42.0)
    assert data["remaining_usd"] == pytest.approx(42.0)


@pytest.mark.asyncio
async def test_cost_status_exceeded_when_over_cap(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """exceeded=True and remaining_usd=0 when spend surpasses the cap."""
    customer_data = await _create_customer_via_api(client)
    customer_id = uuid.UUID(customer_data["id"])

    # Low cap.
    policy = RemediationPolicy(
        customer_id=customer_id,
        max_cost_usd_per_month=5.0,
    )
    db_session.add(policy)
    await db_session.commit()

    from sqlalchemy import select

    from backend.models.customer import Customer

    customer_row = (
        await db_session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one()

    await _seed_run(db_session, customer_row, cost_usd=8.0)

    resp = await client.get(f"/api/customers/{customer_data['id']}/cost-status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["spent_usd"] == pytest.approx(8.0)
    assert data["cap_usd"] == pytest.approx(5.0)
    assert data["remaining_usd"] == pytest.approx(0.0)
    assert data["exceeded"] is True


@pytest.mark.asyncio
async def test_cost_status_only_current_month_counts(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Runs from a previous month are excluded from the spend aggregate."""
    now = datetime.now(UTC)
    last_month_ts = datetime(
        now.year if now.month > 1 else now.year - 1,
        now.month - 1 if now.month > 1 else 12,
        15,
        tzinfo=UTC,
    )

    customer_data = await _create_customer_via_api(client)
    customer_id = uuid.UUID(customer_data["id"])

    from sqlalchemy import select

    from backend.models.customer import Customer

    customer_row = (
        await db_session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one()

    # Last month — should not count.
    await _seed_run(db_session, customer_row, cost_usd=50.0, created_at=last_month_ts)
    # This month — should count.
    await _seed_run(db_session, customer_row, cost_usd=3.0, created_at=now)

    resp = await client.get(f"/api/customers/{customer_data['id']}/cost-status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["spent_usd"] == pytest.approx(3.0)
