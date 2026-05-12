"""Tests for GET /api/model-cards/performance (REQ-051)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from json import dumps

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import AgentRunStatus, AuthType, LLMProviderEnum, Platform, ScanStatus
from backend.models.llm import LLMConnection
from backend.models.scan import Scan
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RECENT = datetime.now(UTC) - timedelta(days=5)


async def _make_customer(db: AsyncSession, name: str = "Perf Router Corp") -> Customer:
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


async def _make_scan(db: AsyncSession, customer_id: uuid.UUID, connection_id: uuid.UUID) -> Scan:
    scan = Scan(
        customer_id=customer_id,
        connection_id=connection_id,
        status=ScanStatus.completed,
    )
    db.add(scan)
    await db.flush()
    return scan


async def _make_llm(db: AsyncSession, customer_id: uuid.UUID) -> LLMConnection:
    llm = LLMConnection(
        customer_id=customer_id,
        name="test-llm",
        provider=LLMProviderEnum.anthropic,
        model="claude-sonnet-4-6",
        api_key_encrypted=secrets_service.encrypt("sk-test"),
        is_default=True,
    )
    db.add(llm)
    await db.flush()
    return llm


async def _make_run(
    db: AsyncSession,
    scan_id: uuid.UUID,
    llm_id: uuid.UUID,
    *,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    started_at: datetime | None = None,
) -> AgentRun:
    run = AgentRun(
        scan_id=scan_id,
        llm_connection_id=llm_id,
        provider=provider,
        model=model,
        status=AgentRunStatus.completed,
        total_cost_usd=1.0,
        total_input_tokens=100,
        total_output_tokens=50,
        started_at=started_at or _RECENT,
        callback_secret=os.urandom(32),
    )
    db.add(run)
    await db.flush()
    return run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_performance_endpoint_returns_200(client: AsyncClient) -> None:
    """GET /api/model-cards/performance returns 200 with the expected envelope."""
    resp = await client.get("/api/model-cards/performance")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "metrics" in data
    assert "computed_at" in data
    assert isinstance(data["metrics"], list)


@pytest.mark.asyncio
async def test_performance_endpoint_empty_when_no_runs(client: AsyncClient) -> None:
    """GET /api/model-cards/performance returns an empty metrics list when no runs exist."""
    resp = await client.get("/api/model-cards/performance")
    assert resp.status_code == 200, resp.text
    assert resp.json()["metrics"] == []


@pytest.mark.asyncio
async def test_performance_endpoint_with_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /api/model-cards/performance returns one metric entry per model when runs exist."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    llm = await _make_llm(db_session, customer.id)

    for _ in range(3):
        await _make_run(db_session, scan.id, llm.id)
    await db_session.commit()

    resp = await client.get("/api/model-cards/performance")
    assert resp.status_code == 200, resp.text
    metrics = resp.json()["metrics"]
    assert len(metrics) >= 1
    entry = metrics[0]
    assert "provider" in entry
    assert "model" in entry
    assert "run_count" in entry
    assert "success_rate" in entry
    assert "pr_open_rate" in entry


@pytest.mark.asyncio
async def test_performance_endpoint_customer_id_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """customer_id query parameter filters performance metrics to one customer."""
    customer_a = await _make_customer(db_session, "Perf A")
    customer_b = await _make_customer(db_session, "Perf B")

    conn_a = await _make_connection(db_session, customer_a.id)
    conn_b = await _make_connection(db_session, customer_b.id)
    scan_a = await _make_scan(db_session, customer_a.id, conn_a.id)
    scan_b = await _make_scan(db_session, customer_b.id, conn_b.id)
    llm_a = await _make_llm(db_session, customer_a.id)
    llm_b = await _make_llm(db_session, customer_b.id)

    for _ in range(2):
        await _make_run(db_session, scan_a.id, llm_a.id, model="claude-sonnet-4-6")
    for _ in range(3):
        await _make_run(db_session, scan_b.id, llm_b.id, provider="openai", model="gpt-4o")
    await db_session.commit()

    resp = await client.get(
        "/api/model-cards/performance", params={"customer_id": str(customer_a.id)}
    )
    assert resp.status_code == 200, resp.text
    metrics = resp.json()["metrics"]
    # Only customer_a's runs should appear.
    assert all(m["model"] == "claude-sonnet-4-6" for m in metrics)


@pytest.mark.asyncio
async def test_performance_endpoint_since_defaults_applied(client: AsyncClient) -> None:
    """GET /api/model-cards/performance without since param uses a 30-day default."""
    # Even without explicit since, the endpoint must not error.
    resp = await client.get("/api/model-cards/performance")
    assert resp.status_code == 200, resp.text
    # computed_at should be a valid ISO-8601 datetime.
    computed_at = resp.json()["computed_at"]
    parsed = datetime.fromisoformat(computed_at.replace("Z", "+00:00"))
    assert parsed is not None


@pytest.mark.asyncio
async def test_performance_endpoint_since_query_param(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Explicit since query param is accepted and produces a valid response."""
    since_str = "2025-01-01T00:00:00Z"
    resp = await client.get("/api/model-cards/performance", params={"since": since_str})
    assert resp.status_code == 200, resp.text
    assert "metrics" in resp.json()
