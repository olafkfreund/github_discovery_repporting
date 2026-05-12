from __future__ import annotations

"""Tests for the agent-runs CRUD endpoints (issue #27).

POST   /api/scans/{scan_id}/agent-runs
GET    /api/agent-runs
GET    /api/agent-runs/estimate
GET    /api/agent-runs/{id}
POST   /api/agent-runs/{id}/cancel

The SSE streaming endpoint is covered in test_agent_runs_sse.py.
"""

import json
import secrets
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun, AgentStep
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import (
    AgentRunStatus,
    AgentStepType,
    AuthType,
    Category,
    CheckStatus,
    LLMProviderEnum,
    Platform,
    ScanStatus,
    Severity,
)
from backend.models.finding import Finding
from backend.models.llm import LLMConnection
from backend.models.scan import Scan
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, suffix: str = "") -> Customer:
    uid = uuid.uuid4().hex[:8]
    customer = Customer(name=f"ARCorp {uid}{suffix}", slug=f"arcorp-{uid}{suffix}")
    db.add(customer)
    await db.flush()
    return customer


async def _make_connection(db: AsyncSession, customer_id: uuid.UUID) -> PlatformConnection:
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


async def _make_llm(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    model: str = "claude-sonnet-4-6",
    is_default: bool = True,
) -> LLMConnection:
    llm = LLMConnection(
        customer_id=customer_id,
        name=f"llm-{uuid.uuid4().hex[:6]}",
        provider=LLMProviderEnum.anthropic,
        model=model,
        is_default=is_default,
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
    scan = Scan(
        customer_id=customer_id,
        connection_id=connection_id,
        status=status,
    )
    db.add(scan)
    await db.flush()
    return scan


async def _make_agent_run(
    db: AsyncSession,
    scan_id: uuid.UUID,
    llm_id: uuid.UUID,
    *,
    status: AgentRunStatus = AgentRunStatus.running,
) -> AgentRun:
    run = AgentRun(
        scan_id=scan_id,
        llm_connection_id=llm_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        status=status,
        runtime_mode="backend",
        callback_secret=secrets.token_bytes(32),
    )
    db.add(run)
    await db.flush()
    return run


async def _make_finding(
    db: AsyncSession,
    scan_id: uuid.UUID,
    *,
    status: CheckStatus = CheckStatus.failed,
) -> Finding:
    finding = Finding(
        scan_id=scan_id,
        category=Category.cicd,
        check_id="CICD-008",
        check_name="Pinned action versions",
        severity=Severity.medium,
        status=status,
        weight=1.0,
        score=0.0,
    )
    db.add(finding)
    await db.flush()
    return finding


async def _make_step(
    db: AsyncSession,
    agent_run_id: uuid.UUID,
    step_index: int = 0,
    step_type: AgentStepType = AgentStepType.llm_call,
) -> AgentStep:
    step = AgentStep(
        agent_run_id=agent_run_id,
        step_index=step_index,
        step_type=step_type,
        input_tokens=10,
        output_tokens=20,
        latency_ms=100,
        status="ok",
    )
    db.add(step)
    await db.flush()
    return step


# ---------------------------------------------------------------------------
# POST /api/scans/{scan_id}/agent-runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_happy_path(db_session: AsyncSession, client: AsyncClient) -> None:
    """POST trigger returns 201 with status=pending for a valid scan + LLM."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await db_session.commit()

    with patch(
        "backend.services.agent_service.trigger_backend_run",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            f"/api/scans/{scan.id}/agent-runs",
            json={"llm_connection_id": str(llm.id)},
        )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    assert data["scan_id"] == str(scan.id)
    assert data["llm_connection_id"] == str(llm.id)


@pytest.mark.asyncio
async def test_trigger_scan_not_found(db_session: AsyncSession, client: AsyncClient) -> None:
    """POST trigger returns 404 when the scan does not exist."""
    customer = await _make_customer(db_session)
    llm = await _make_llm(db_session, customer.id)
    await db_session.commit()

    with patch(
        "backend.services.agent_service.trigger_backend_run",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            f"/api/scans/{uuid.uuid4()}/agent-runs",
            json={"llm_connection_id": str(llm.id)},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_scan_not_completed(db_session: AsyncSession, client: AsyncClient) -> None:
    """POST trigger returns 409 when scan is not in 'completed' status."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id, status=ScanStatus.scanning)
    await db_session.commit()

    with patch(
        "backend.services.agent_service.trigger_backend_run",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            f"/api/scans/{scan.id}/agent-runs",
            json={"llm_connection_id": str(llm.id)},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_trigger_llm_not_found(db_session: AsyncSession, client: AsyncClient) -> None:
    """POST trigger returns 404 when the LLM connection does not exist."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await db_session.commit()

    with patch(
        "backend.services.agent_service.trigger_backend_run",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            f"/api/scans/{scan.id}/agent-runs",
            json={"llm_connection_id": str(uuid.uuid4())},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_active_run_exists(db_session: AsyncSession, client: AsyncClient) -> None:
    """POST trigger returns 409 when a non-terminal run already exists for the scan."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.running)
    await db_session.commit()

    with patch(
        "backend.services.agent_service.trigger_backend_run",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            f"/api/scans/{scan.id}/agent-runs",
            json={"llm_connection_id": str(llm.id)},
        )

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/agent-runs — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_no_filters(db_session: AsyncSession, client: AsyncClient) -> None:
    """GET /api/agent-runs returns all runs ordered by started_at desc, default limit 50."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.completed)
    await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.cancelled)
    await db_session.commit()

    resp = await client.get("/api/agent-runs")
    assert resp.status_code == 200
    data = resp.json()
    # Both runs should be returned (no filter).
    assert len(data) >= 2  # noqa: PLR2004


@pytest.mark.asyncio
async def test_list_filter_scan_id(db_session: AsyncSession, client: AsyncClient) -> None:
    """GET /api/agent-runs?scan_id=... returns only that scan's runs."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan1 = await _make_scan(db_session, customer.id, conn.id)
    scan2 = await _make_scan(db_session, customer.id, conn.id)
    run1 = await _make_agent_run(db_session, scan1.id, llm.id, status=AgentRunStatus.completed)
    await _make_agent_run(db_session, scan2.id, llm.id, status=AgentRunStatus.completed)
    await db_session.commit()

    resp = await client.get("/api/agent-runs", params={"scan_id": str(scan1.id)})
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert str(run1.id) in ids
    # scan2's run should not be present
    assert all(r["scan_id"] == str(scan1.id) for r in resp.json())


@pytest.mark.asyncio
async def test_list_filter_customer_id(db_session: AsyncSession, client: AsyncClient) -> None:
    """GET /api/agent-runs?customer_id=... joins through scans."""
    c1 = await _make_customer(db_session, "A")
    c2 = await _make_customer(db_session, "B")
    conn1 = await _make_connection(db_session, c1.id)
    conn2 = await _make_connection(db_session, c2.id)
    llm1 = await _make_llm(db_session, c1.id)
    llm2 = await _make_llm(db_session, c2.id)
    scan1 = await _make_scan(db_session, c1.id, conn1.id)
    scan2 = await _make_scan(db_session, c2.id, conn2.id)
    run1 = await _make_agent_run(db_session, scan1.id, llm1.id, status=AgentRunStatus.completed)
    await _make_agent_run(db_session, scan2.id, llm2.id, status=AgentRunStatus.completed)
    await db_session.commit()

    resp = await client.get("/api/agent-runs", params={"customer_id": str(c1.id)})
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert str(run1.id) in ids
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_list_filter_status(db_session: AsyncSession, client: AsyncClient) -> None:
    """GET /api/agent-runs?status=... returns only that status."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run_ok = await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.completed)
    await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.cancelled)
    await db_session.commit()

    resp = await client.get("/api/agent-runs", params={"status": "completed"})
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert str(run_ok.id) in ids
    assert all(r["status"] == "completed" for r in resp.json())


# ---------------------------------------------------------------------------
# GET /api/agent-runs/{id} — detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_detail_happy_path(db_session: AsyncSession, client: AsyncClient) -> None:
    """GET /api/agent-runs/{id} returns run with steps ordered by step_index asc."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.completed)
    # Insert steps out of order to verify sorting.
    await _make_step(db_session, run.id, step_index=2)
    await _make_step(db_session, run.id, step_index=0)
    await _make_step(db_session, run.id, step_index=1)
    await db_session.commit()

    resp = await client.get(f"/api/agent-runs/{run.id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(run.id)
    assert "steps" in data
    assert "actions" in data
    step_indices = [s["step_index"] for s in data["steps"]]
    assert step_indices == sorted(step_indices), "steps must be ordered by step_index asc"


@pytest.mark.asyncio
async def test_get_detail_not_found(client: AsyncClient) -> None:
    """GET /api/agent-runs/{id} returns 404 for a missing run."""
    resp = await client.get(f"/api/agent-runs/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/agent-runs/{id}/cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_running(db_session: AsyncSession, client: AsyncClient) -> None:
    """POST cancel on a running run returns status=cancelled."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.running)
    await db_session.commit()

    resp = await client.post(f"/api/agent-runs/{run.id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_terminal_idempotent(db_session: AsyncSession, client: AsyncClient) -> None:
    """POST cancel on a terminal run is idempotent and returns the current state."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.completed)
    await db_session.commit()

    resp = await client.post(f"/api/agent-runs/{run.id}/cancel")
    assert resp.status_code == 200, resp.text
    # Status must remain 'completed', not be changed to 'cancelled'.
    assert resp.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# GET /api/agent-runs/estimate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_returns_shape(db_session: AsyncSession, client: AsyncClient) -> None:
    """GET /api/agent-runs/estimate returns min_usd, max_usd, expected_tokens."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await _make_finding(db_session, scan.id, status=CheckStatus.failed)
    await db_session.commit()

    resp = await client.get("/api/agent-runs/estimate", params={"scan_id": str(scan.id)})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "min_usd" in data
    assert "max_usd" in data
    assert "expected_tokens" in data
    assert isinstance(data["min_usd"], float)
    assert isinstance(data["max_usd"], float)
    assert isinstance(data["expected_tokens"], int)
    assert data["max_usd"] >= data["min_usd"]


@pytest.mark.asyncio
async def test_estimate_scan_not_found(client: AsyncClient) -> None:
    """GET /api/agent-runs/estimate returns 404 for a missing scan."""
    resp = await client.get(
        "/api/agent-runs/estimate",
        params={"scan_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
