from __future__ import annotations

"""Unit tests for backend.services.cost_cap_service.

Uses the in-memory SQLite engine from conftest.py.  Agent-run ``created_at``
timestamps are set explicitly via a follow-up UPDATE so that the month-window
filtering logic can be exercised without relying on wall-clock time.
"""

import secrets
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import AuthType, LLMProviderEnum, Platform, ScanStatus
from backend.models.llm import LLMConnection
from backend.models.remediation_policy import RemediationPolicy
from backend.models.scan import Scan
from backend.services import cost_cap_service as svc
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Test fixtures / factories
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, suffix: str = "") -> Customer:
    uid = uuid.uuid4().hex[:8]
    customer = Customer(name=f"CostCorp {uid}{suffix}", slug=f"costcorp-{uid}{suffix}")
    db.add(customer)
    await db.flush()
    return customer


async def _make_connection(db: AsyncSession, customer_id: uuid.UUID) -> PlatformConnection:
    import json

    conn = PlatformConnection(
        customer_id=customer_id,
        platform=Platform.github,
        display_name="Test GitHub",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(json.dumps({"token": "ghp_test"})),
        org_or_group="test-org",
        is_active=True,
    )
    db.add(conn)
    await db.flush()
    return conn


async def _make_llm(db: AsyncSession, customer_id: uuid.UUID) -> LLMConnection:
    llm = LLMConnection(
        customer_id=customer_id,
        name=f"llm-{uuid.uuid4().hex[:6]}",
        provider=LLMProviderEnum.anthropic,
        model="claude-sonnet-4-6",
        is_default=True,
    )
    db.add(llm)
    await db.flush()
    return llm


async def _make_scan(
    db: AsyncSession,
    customer_id: uuid.UUID,
    connection_id: uuid.UUID,
    *,
    status: ScanStatus = ScanStatus.completed,
) -> Scan:
    scan = Scan(customer_id=customer_id, connection_id=connection_id, status=status)
    db.add(scan)
    await db.flush()
    return scan


async def _make_agent_run(
    db: AsyncSession,
    scan_id: uuid.UUID,
    llm_id: uuid.UUID,
    *,
    cost_usd: float = 0.0,
    created_at: datetime | None = None,
) -> AgentRun:
    """Insert an AgentRun and optionally back-date its ``created_at``."""
    run = AgentRun(
        scan_id=scan_id,
        llm_connection_id=llm_id,
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
        # Override the DB default with an explicit timestamp.
        await db.execute(
            update(AgentRun).where(AgentRun.id == run.id).values(created_at=created_at)
        )
        await db.flush()
        await db.refresh(run)

    return run


async def _add_policy(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    max_cost_usd_per_month: float,
) -> RemediationPolicy:
    policy = RemediationPolicy(
        customer_id=customer_id,
        max_cost_usd_per_month=max_cost_usd_per_month,
    )
    db.add(policy)
    await db.flush()
    return policy


# ---------------------------------------------------------------------------
# compute_monthly_cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_monthly_cost_empty_customer(db_session: AsyncSession) -> None:
    """Returns 0.0 when the customer has no runs at all."""
    customer = await _make_customer(db_session)
    await db_session.commit()

    result = await svc.compute_monthly_cost(db_session, customer.id)

    assert result == 0.0


@pytest.mark.asyncio
async def test_compute_monthly_cost_single_run(db_session: AsyncSession) -> None:
    """Returns the cost of a single agent run."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await _make_agent_run(db_session, scan.id, llm.id, cost_usd=2.50)
    await db_session.commit()

    result = await svc.compute_monthly_cost(db_session, customer.id)

    assert result == pytest.approx(2.50)


@pytest.mark.asyncio
async def test_compute_monthly_cost_multiple_runs_sum(db_session: AsyncSession) -> None:
    """Sums all agent-run costs for the customer."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    for _ in range(3):
        await _make_agent_run(db_session, scan.id, llm.id, cost_usd=1.25)
    await db_session.commit()

    result = await svc.compute_monthly_cost(db_session, customer.id)

    assert result == pytest.approx(3.75)


@pytest.mark.asyncio
async def test_compute_monthly_cost_since_cutoff(db_session: AsyncSession) -> None:
    """Runs before the ``since`` boundary are excluded from the sum."""
    now = datetime.now(UTC)
    month_start = svc._month_start_utc(now)
    last_month = datetime(
        now.year if now.month > 1 else now.year - 1,
        now.month - 1 if now.month > 1 else 12,
        15,
        tzinfo=UTC,
    )

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    # One run last month (should be excluded by default since).
    await _make_agent_run(db_session, scan.id, llm.id, cost_usd=50.0, created_at=last_month)
    # One run this month (should be included).
    await _make_agent_run(db_session, scan.id, llm.id, cost_usd=5.0, created_at=now)
    await db_session.commit()

    result = await svc.compute_monthly_cost(db_session, customer.id, since=month_start)

    assert result == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_compute_monthly_cost_customer_no_scans(db_session: AsyncSession) -> None:
    """Returns 0.0 for a customer that exists but has no scans."""
    customer = await _make_customer(db_session)
    await db_session.commit()

    result = await svc.compute_monthly_cost(db_session, customer.id)

    assert result == 0.0


# ---------------------------------------------------------------------------
# get_cost_cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cost_cap_no_policy_returns_default(db_session: AsyncSession) -> None:
    """Returns 100.0 when no RemediationPolicy exists for the customer."""
    customer = await _make_customer(db_session)
    await db_session.commit()

    cap = await svc.get_cost_cap(db_session, customer.id)

    assert cap == 100.0


@pytest.mark.asyncio
async def test_get_cost_cap_policy_sets_cap(db_session: AsyncSession) -> None:
    """Returns the policy's ``max_cost_usd_per_month`` when a policy row exists."""
    customer = await _make_customer(db_session)
    await _add_policy(db_session, customer.id, max_cost_usd_per_month=42.0)
    await db_session.commit()

    cap = await svc.get_cost_cap(db_session, customer.id)

    assert cap == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# check — CostCapState
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_empty_customer_not_exceeded(db_session: AsyncSession) -> None:
    """Empty customer: remaining=cap, exceeded=False."""
    customer = await _make_customer(db_session)
    await db_session.commit()

    state = await svc.check(db_session, customer.id)

    assert state.customer_id == customer.id
    assert state.spent_usd == 0.0
    assert state.cap_usd == 100.0
    assert state.remaining_usd == 100.0
    assert state.exceeded is False


@pytest.mark.asyncio
async def test_check_spent_equals_cap_exceeded_true(db_session: AsyncSession) -> None:
    """When spent exactly equals cap, exceeded is True."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await _add_policy(db_session, customer.id, max_cost_usd_per_month=10.0)
    await _make_agent_run(db_session, scan.id, llm.id, cost_usd=10.0)
    await db_session.commit()

    state = await svc.check(db_session, customer.id)

    assert state.spent_usd == pytest.approx(10.0)
    assert state.cap_usd == pytest.approx(10.0)
    assert state.exceeded is True
    assert state.remaining_usd == 0.0


@pytest.mark.asyncio
async def test_check_spent_exceeds_cap_remaining_zero(db_session: AsyncSession) -> None:
    """When spent exceeds cap, remaining_usd clamps to 0.0 and exceeded=True."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await _add_policy(db_session, customer.id, max_cost_usd_per_month=5.0)
    await _make_agent_run(db_session, scan.id, llm.id, cost_usd=7.50)
    await db_session.commit()

    state = await svc.check(db_session, customer.id)

    assert state.spent_usd == pytest.approx(7.50)
    assert state.cap_usd == pytest.approx(5.0)
    assert state.exceeded is True
    assert state.remaining_usd == 0.0


@pytest.mark.asyncio
async def test_check_partial_spend_not_exceeded(db_session: AsyncSession) -> None:
    """Partial spend: exceeded=False, remaining_usd correctly computed."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await _add_policy(db_session, customer.id, max_cost_usd_per_month=100.0)
    await _make_agent_run(db_session, scan.id, llm.id, cost_usd=30.0)
    await db_session.commit()

    state = await svc.check(db_session, customer.id)

    assert state.spent_usd == pytest.approx(30.0)
    assert state.remaining_usd == pytest.approx(70.0)
    assert state.exceeded is False


@pytest.mark.asyncio
async def test_check_month_start_is_utc_first_of_month(db_session: AsyncSession) -> None:
    """CostCapState.month_start is the first day of the current UTC month."""
    customer = await _make_customer(db_session)
    await db_session.commit()

    state = await svc.check(db_session, customer.id)
    now = datetime.now(UTC)

    assert state.month_start.year == now.year
    assert state.month_start.month == now.month
    assert state.month_start.day == 1
    assert state.month_start.hour == 0
    assert state.month_start.tzinfo is not None
