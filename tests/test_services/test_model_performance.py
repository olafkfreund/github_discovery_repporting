"""Unit tests for model_performance_service (REQ-051)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from json import dumps

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun, RemediationAction
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import (
    AgentRunStatus,
    AuthType,
    Platform,
    RemediationActionStatus,
    ScanStatus,
)
from backend.models.finding import Finding
from backend.models.llm import LLMConnection
from backend.models.scan import Scan
from backend.services import model_performance_service as svc
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC)
_RECENT = _NOW - timedelta(days=10)
_OLD = _NOW - timedelta(days=60)


async def _make_customer(db: AsyncSession, name: str = "Perf Corp") -> Customer:
    slug = name.lower().replace(" ", "-")
    customer = Customer(name=name, slug=slug)
    db.add(customer)
    await db.flush()
    return customer


async def _make_connection(db: AsyncSession, customer_id: uuid.UUID) -> PlatformConnection:
    conn = PlatformConnection(
        customer_id=customer_id,
        platform=Platform.github,
        display_name="Test Conn",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(dumps({"token": "t"})),
        org_or_group="test-org",
    )
    db.add(conn)
    await db.flush()
    return conn


async def _make_scan(
    db: AsyncSession,
    customer_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> Scan:
    scan = Scan(
        customer_id=customer_id,
        connection_id=connection_id,
        status=ScanStatus.completed,
    )
    db.add(scan)
    await db.flush()
    return scan


async def _make_llm_connection(db: AsyncSession, customer_id: uuid.UUID) -> LLMConnection:
    from backend.models.enums import LLMProviderEnum

    llm_conn = LLMConnection(
        customer_id=customer_id,
        name="test-llm",
        provider=LLMProviderEnum.anthropic,
        model="claude-sonnet-4-6",
        api_key_encrypted=secrets_service.encrypt("sk-test"),
        is_default=True,
    )
    db.add(llm_conn)
    await db.flush()
    return llm_conn


async def _make_agent_run(
    db: AsyncSession,
    scan_id: uuid.UUID,
    llm_connection_id: uuid.UUID,
    *,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    status: AgentRunStatus = AgentRunStatus.completed,
    total_cost_usd: float = 1.00,
    total_input_tokens: int = 1000,
    total_output_tokens: int = 500,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> AgentRun:
    run = AgentRun(
        scan_id=scan_id,
        llm_connection_id=llm_connection_id,
        provider=provider,
        model=model,
        status=status,
        total_cost_usd=total_cost_usd,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        started_at=started_at or _RECENT,
        finished_at=finished_at,
        callback_secret=os.urandom(32),
    )
    db.add(run)
    await db.flush()
    return run


async def _make_finding(
    db: AsyncSession,
    scan_id: uuid.UUID,
) -> Finding:
    from backend.models.enums import Category, CheckStatus, Severity

    finding = Finding(
        scan_id=scan_id,
        category=Category.cicd,
        check_id="CICD-001",
        check_name="Test check",
        severity=Severity.high,
        status=CheckStatus.failed,
    )
    db.add(finding)
    await db.flush()
    return finding


async def _make_remediation_action(
    db: AsyncSession,
    agent_run_id: uuid.UUID,
    finding_id: uuid.UUID,
    *,
    status: RemediationActionStatus = RemediationActionStatus.opened,
) -> RemediationAction:
    action = RemediationAction(
        agent_run_id=agent_run_id,
        finding_id=finding_id,
        check_id="CICD-001",
        status=status,
    )
    db.add(action)
    await db.flush()
    return action


# ---------------------------------------------------------------------------
# Basic aggregation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_metrics_returns_two_entries_for_two_models(
    db_session: AsyncSession,
) -> None:
    """compute_metrics groups by (provider, model) and returns one entry per unique pair."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    llm = await _make_llm_connection(db_session, customer.id)

    for _ in range(5):
        await _make_agent_run(
            db_session,
            scan.id,
            llm.id,
            provider="anthropic",
            model="claude-sonnet-4-6",
        )
    for _ in range(3):
        await _make_agent_run(
            db_session,
            scan.id,
            llm.id,
            provider="openai",
            model="gpt-4o",
        )

    results = await svc.compute_metrics(db_session)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_compute_metrics_ordered_by_run_count_desc(
    db_session: AsyncSession,
) -> None:
    """Results must be ordered by run_count descending."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    llm = await _make_llm_connection(db_session, customer.id)

    for _ in range(5):
        await _make_agent_run(db_session, scan.id, llm.id, model="claude-sonnet-4-6")
    for _ in range(3):
        await _make_agent_run(db_session, scan.id, llm.id, model="gpt-4o", provider="openai")

    results = await svc.compute_metrics(db_session)
    assert results[0].run_count >= results[1].run_count


@pytest.mark.asyncio
async def test_compute_metrics_run_count_correct(
    db_session: AsyncSession,
) -> None:
    """run_count must equal the number of runs inserted for each model."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    llm = await _make_llm_connection(db_session, customer.id)

    for _ in range(5):
        await _make_agent_run(db_session, scan.id, llm.id, model="claude-sonnet-4-6")

    results = await svc.compute_metrics(db_session)
    assert len(results) == 1
    assert results[0].run_count == 5


@pytest.mark.asyncio
async def test_compute_metrics_avg_cost_correct(
    db_session: AsyncSession,
) -> None:
    """avg_cost_usd must be the arithmetic mean of total_cost_usd per run."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    llm = await _make_llm_connection(db_session, customer.id)

    costs = [1.00, 2.00, 3.00, 4.00, 5.00]
    for cost in costs:
        await _make_agent_run(
            db_session, scan.id, llm.id, model="claude-sonnet-4-6", total_cost_usd=cost
        )

    results = await svc.compute_metrics(db_session)
    assert len(results) == 1
    expected_avg = sum(costs) / len(costs)
    assert abs(results[0].avg_cost_usd - expected_avg) < 1e-6


@pytest.mark.asyncio
async def test_compute_metrics_success_rate_correct(
    db_session: AsyncSession,
) -> None:
    """success_rate must be completed_count / run_count."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    llm = await _make_llm_connection(db_session, customer.id)

    # 3 completed, 2 failed
    for _ in range(3):
        await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.completed)
    for _ in range(2):
        await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.failed)

    results = await svc.compute_metrics(db_session)
    assert len(results) == 1
    assert abs(results[0].success_rate - 0.6) < 1e-6


@pytest.mark.asyncio
async def test_compute_metrics_pr_open_rate_correct(
    db_session: AsyncSession,
) -> None:
    """pr_open_rate must be fraction of runs with >= 1 opened RemediationAction."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    llm = await _make_llm_connection(db_session, customer.id)
    finding = await _make_finding(db_session, scan.id)

    # 2 runs with opened PR, 3 without
    for _ in range(2):
        run = await _make_agent_run(db_session, scan.id, llm.id)
        await _make_remediation_action(
            db_session, run.id, finding.id, status=RemediationActionStatus.opened
        )
    for _ in range(3):
        await _make_agent_run(db_session, scan.id, llm.id)

    results = await svc.compute_metrics(db_session)
    assert len(results) == 1
    assert abs(results[0].pr_open_rate - 0.4) < 1e-6


# ---------------------------------------------------------------------------
# Filter: customer_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_metrics_customer_id_filter(
    db_session: AsyncSession,
) -> None:
    """customer_id filter narrows results to only that customer's scans."""
    customer_a = await _make_customer(db_session, "Customer A")
    customer_b = await _make_customer(db_session, "Customer B")

    conn_a = await _make_connection(db_session, customer_a.id)
    conn_b = await _make_connection(db_session, customer_b.id)
    scan_a = await _make_scan(db_session, customer_a.id, conn_a.id)
    scan_b = await _make_scan(db_session, customer_b.id, conn_b.id)

    llm_a = await _make_llm_connection(db_session, customer_a.id)
    llm_b = await _make_llm_connection(db_session, customer_b.id)

    # 4 runs for customer_a, 2 for customer_b
    for _ in range(4):
        await _make_agent_run(db_session, scan_a.id, llm_a.id, model="claude-sonnet-4-6")
    for _ in range(2):
        await _make_agent_run(db_session, scan_b.id, llm_b.id, model="gpt-4o", provider="openai")

    results_a = await svc.compute_metrics(db_session, customer_id=customer_a.id)
    assert len(results_a) == 1
    assert results_a[0].run_count == 4
    assert results_a[0].model == "claude-sonnet-4-6"

    results_b = await svc.compute_metrics(db_session, customer_id=customer_b.id)
    assert len(results_b) == 1
    assert results_b[0].run_count == 2
    assert results_b[0].model == "gpt-4o"


# ---------------------------------------------------------------------------
# Filter: since
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_metrics_since_filter_excludes_older_runs(
    db_session: AsyncSession,
) -> None:
    """since filter excludes runs with started_at before the cutoff."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    llm = await _make_llm_connection(db_session, customer.id)

    # 3 recent runs, 2 old runs
    for _ in range(3):
        await _make_agent_run(db_session, scan.id, llm.id, started_at=_RECENT)
    for _ in range(2):
        await _make_agent_run(db_session, scan.id, llm.id, started_at=_OLD)

    cutoff = _NOW - timedelta(days=30)
    results = await svc.compute_metrics(db_session, since=cutoff)
    assert len(results) == 1
    assert results[0].run_count == 3


# ---------------------------------------------------------------------------
# Empty result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_metrics_empty_when_no_runs(
    db_session: AsyncSession,
) -> None:
    """compute_metrics returns an empty list when there are no AgentRun rows."""
    results = await svc.compute_metrics(db_session)
    assert results == []


@pytest.mark.asyncio
async def test_compute_metrics_empty_for_unmatched_customer_id(
    db_session: AsyncSession,
) -> None:
    """compute_metrics returns empty list when customer_id matches no scans."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    llm = await _make_llm_connection(db_session, customer.id)
    await _make_agent_run(db_session, scan.id, llm.id)

    other_customer_id = uuid.uuid4()
    results = await svc.compute_metrics(db_session, customer_id=other_customer_id)
    assert results == []
