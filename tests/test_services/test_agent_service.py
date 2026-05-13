from __future__ import annotations

"""Unit tests for backend.services.agent_service.

All DB interactions use the in-memory SQLite engine from conftest.py.
All background-task scheduling is verified by inspecting return types and
mock calls — no actual asyncio tasks are awaited in these tests.
"""

import asyncio
import secrets
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import (
    AgentRunStatus,
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
from backend.services import agent_service as svc
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Test helpers / factories — mirrors test_agent_runs.py style
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, suffix: str = "") -> Customer:
    uid = uuid.uuid4().hex[:8]
    customer = Customer(name=f"SvcCorp {uid}{suffix}", slug=f"svccorp-{uid}{suffix}")
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


# ---------------------------------------------------------------------------
# create_agent_run — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_run_happy_path(db_session: AsyncSession) -> None:
    """create_agent_run returns a pending AgentRun on valid input."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await db_session.commit()

    run = await svc.create_agent_run(
        db_session,
        scan_id=scan.id,
        llm_connection_id=llm.id,
    )

    assert run.id is not None
    assert run.scan_id == scan.id
    assert run.llm_connection_id == llm.id
    assert run.status == AgentRunStatus.pending
    assert run.runtime_mode == "backend"
    assert len(run.callback_secret) == 32
    # Provider + model snapshotted.
    assert run.provider == "anthropic"
    assert run.model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# create_agent_run — validation failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_run_scan_not_found(db_session: AsyncSession) -> None:
    """create_agent_run raises 404 when scan does not exist."""
    from fastapi import HTTPException

    customer = await _make_customer(db_session)
    llm = await _make_llm(db_session, customer.id)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_agent_run(
            db_session,
            scan_id=uuid.uuid4(),
            llm_connection_id=llm.id,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_agent_run_scan_not_completed(db_session: AsyncSession) -> None:
    """create_agent_run raises 409 when scan is not in 'completed' state."""
    from fastapi import HTTPException

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id, status=ScanStatus.scanning)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_agent_run(
            db_session,
            scan_id=scan.id,
            llm_connection_id=llm.id,
        )
    assert exc_info.value.status_code == 409
    assert "scanning" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_agent_run_llm_not_found(db_session: AsyncSession) -> None:
    """create_agent_run raises 404 when LLMConnection does not exist."""
    from fastapi import HTTPException

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_agent_run(
            db_session,
            scan_id=scan.id,
            llm_connection_id=uuid.uuid4(),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_agent_run_non_terminal_run_exists(db_session: AsyncSession) -> None:
    """create_agent_run raises 409 when a non-terminal run already exists for the scan."""
    from fastapi import HTTPException

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    # Pre-create a running run.
    await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.running)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_agent_run(
            db_session,
            scan_id=scan.id,
            llm_connection_id=llm.id,
        )
    assert exc_info.value.status_code == 409
    assert "running" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_agent_run_terminal_run_allows_new(db_session: AsyncSession) -> None:
    """create_agent_run succeeds when prior run is in a terminal state."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    # Pre-create a completed (terminal) run.
    await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.completed)
    await db_session.commit()

    run = await svc.create_agent_run(
        db_session,
        scan_id=scan.id,
        llm_connection_id=llm.id,
    )
    assert run.status == AgentRunStatus.pending


# ---------------------------------------------------------------------------
# cancel_agent_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_agent_run_running(db_session: AsyncSession) -> None:
    """cancel_agent_run sets status to cancelled and triggers the cancel event."""
    from backend.services.event_bus import get_cancel_registry

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.running)
    await db_session.commit()

    # Register a cancel event so trigger() can find it.
    registry = get_cancel_registry()
    cancel_event = registry.get_or_create(run.id)

    updated = await svc.cancel_agent_run(db_session, run.id)

    assert updated.status == AgentRunStatus.cancelled
    assert cancel_event.is_set()

    # Cleanup registry.
    registry.cleanup(run.id)


@pytest.mark.asyncio
async def test_cancel_agent_run_already_completed(db_session: AsyncSession) -> None:
    """cancel_agent_run is idempotent when run is already in a terminal state."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.completed)
    await db_session.commit()

    updated = await svc.cancel_agent_run(db_session, run.id)

    # Must remain completed — not changed to cancelled.
    assert updated.status == AgentRunStatus.completed


@pytest.mark.asyncio
async def test_cancel_agent_run_not_found(db_session: AsyncSession) -> None:
    """cancel_agent_run raises 404 for unknown run IDs."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await svc.cancel_agent_run(db_session, uuid.uuid4())
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# estimate_run_cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_run_cost_sane_shape(db_session: AsyncSession) -> None:
    """estimate_run_cost returns expected keys with numeric values."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm(db_session, customer.id, model="claude-sonnet-4-6")
    scan = await _make_scan(db_session, customer.id, conn.id)
    # Add a few failing findings.
    for _ in range(3):
        await _make_finding(db_session, scan.id, status=CheckStatus.failed)
    await db_session.commit()

    result = await svc.estimate_run_cost(db_session, scan.id)

    assert "min_usd" in result
    assert "max_usd" in result
    assert "expected_tokens" in result
    assert result["min_usd"] >= 0.0
    assert result["max_usd"] >= result["min_usd"]
    assert result["expected_tokens"] == 3 * 8_000


@pytest.mark.asyncio
async def test_estimate_run_cost_scan_not_found(db_session: AsyncSession) -> None:
    """estimate_run_cost raises 404 for unknown scan IDs."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await svc.estimate_run_cost(db_session, uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_estimate_run_cost_no_llm_zero_cost(db_session: AsyncSession) -> None:
    """estimate_run_cost returns zero costs when no LLM connection exists."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    await _make_finding(db_session, scan.id)
    await db_session.commit()

    result = await svc.estimate_run_cost(db_session, scan.id)

    # No LLM connection → falls back to "_default" (free/self-hosted).
    assert result["min_usd"] == 0.0
    assert result["max_usd"] == 0.0
    assert result["expected_tokens"] == 8_000


@pytest.mark.asyncio
async def test_estimate_run_cost_known_model_has_nonzero(db_session: AsyncSession) -> None:
    """estimate_run_cost returns nonzero costs for a paid API model."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    await _make_llm(db_session, customer.id, model="claude-opus-4-7")
    scan = await _make_scan(db_session, customer.id, conn.id)
    for _ in range(5):
        await _make_finding(db_session, scan.id)
    await db_session.commit()

    result = await svc.estimate_run_cost(db_session, scan.id)

    # claude-opus-4-7 has non-zero pricing.
    assert result["max_usd"] > 0.0
    assert result["expected_tokens"] == 5 * 8_000


# ---------------------------------------------------------------------------
# trigger_backend_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_backend_run_returns_task(db_session: AsyncSession) -> None:
    """trigger_backend_run returns an asyncio.Task."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.pending)
    await db_session.commit()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    engine.dialect.native_uuid = False  # type: ignore[attr-defined]
    from backend.models.base import Base

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    with patch(
        "backend.agents.runner_backend.run_backend_agent",
        new_callable=AsyncMock,
    ) as mock_runner:
        # Make the mock complete immediately.
        mock_runner.return_value = None
        task = await svc.trigger_backend_run(run, factory)

        assert isinstance(task, asyncio.Task)
        # Allow the task to run (it calls the mock which returns immediately).
        await asyncio.sleep(0)
        # Cancel if still running to avoid dangling tasks.
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    await engine.dispose()


@pytest.mark.asyncio
async def test_trigger_backend_run_schedules_runner(db_session: AsyncSession) -> None:
    """trigger_backend_run calls run_backend_agent with the correct run_id."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id, status=AgentRunStatus.pending)
    await db_session.commit()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    engine.dialect.native_uuid = False  # type: ignore[attr-defined]
    from backend.models.base import Base

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    called_with: list[uuid.UUID] = []

    async def fake_runner(*, agent_run_id: uuid.UUID, db_factory) -> None:  # noqa: ANN001
        called_with.append(agent_run_id)

    with patch("backend.agents.runner_backend.run_backend_agent", side_effect=fake_runner):
        # Also patch the semaphore so it doesn't block.
        sem = asyncio.Semaphore(10)
        with patch("backend.services.task_limiter.get_agent_semaphore", return_value=sem):
            task = await svc.trigger_backend_run(run, factory)
            # Let the event loop process the task.
            await asyncio.sleep(0.01)
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    assert run.id in called_with

    await engine.dispose()


# ---------------------------------------------------------------------------
# create_agent_run — kill switch (issue #46)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_run_global_kill_switch_raises_403(
    db_session: AsyncSession,
) -> None:
    """create_agent_run raises 403 when the global kill switch is engaged."""
    from fastapi import HTTPException

    from backend.schemas.setting import SettingUpdate
    from backend.services import settings_service

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    # Enable global kill switch.
    await settings_service.update_settings(
        db_session, SettingUpdate(global_kill_switch_enabled=True)
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_agent_run(
            db_session,
            scan_id=scan.id,
            llm_connection_id=llm.id,
        )
    assert exc_info.value.status_code == 403
    assert "global" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_agent_run_customer_kill_switch_raises_403(
    db_session: AsyncSession,
) -> None:
    """create_agent_run raises 403 when the customer-level kill switch is engaged."""
    from fastapi import HTTPException

    from backend.models.remediation_policy import RemediationPolicy

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    # Customer-level kill switch on.
    policy = RemediationPolicy(customer_id=customer.id, kill_switch_enabled=True)
    db_session.add(policy)
    await db_session.commit()
    await db_session.refresh(customer)

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_agent_run(
            db_session,
            scan_id=scan.id,
            llm_connection_id=llm.id,
        )
    assert exc_info.value.status_code == 403
    assert "customer" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_agent_run_no_kill_switch_succeeds(
    db_session: AsyncSession,
) -> None:
    """create_agent_run succeeds when both global and customer kill switches are off."""
    from backend.models.remediation_policy import RemediationPolicy

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    policy = RemediationPolicy(customer_id=customer.id, kill_switch_enabled=False)
    db_session.add(policy)
    await db_session.commit()

    run = await svc.create_agent_run(
        db_session,
        scan_id=scan.id,
        llm_connection_id=llm.id,
    )
    assert run.status == AgentRunStatus.pending


# ---------------------------------------------------------------------------
# create_agent_run — cost cap (issue #48)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_run_rejects_when_cost_cap_exceeded(
    db_session: AsyncSession,
) -> None:
    """create_agent_run raises 409 when the monthly cost cap has been exceeded."""
    import secrets as secrets_mod

    from fastapi import HTTPException

    from backend.models.remediation_policy import RemediationPolicy

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    # Policy with a very low cap.
    policy = RemediationPolicy(
        customer_id=customer.id,
        kill_switch_enabled=False,
        max_cost_usd_per_month=10.0,
    )
    db_session.add(policy)

    # Seed an existing completed run that already exceeds the cap.
    existing_run = AgentRun(
        scan_id=scan.id,
        llm_connection_id=llm.id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        status=AgentRunStatus.completed,
        runtime_mode="backend",
        callback_secret=secrets_mod.token_bytes(32),
        total_cost_usd=12.0,
    )
    db_session.add(existing_run)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_agent_run(
            db_session,
            scan_id=scan.id,
            llm_connection_id=llm.id,
        )

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert "cost cap" in detail.lower() or "monthly cost cap" in detail.lower()


@pytest.mark.asyncio
async def test_create_agent_run_cost_cap_not_exceeded_succeeds(
    db_session: AsyncSession,
) -> None:
    """create_agent_run succeeds when spend is below the cap."""
    from backend.models.remediation_policy import RemediationPolicy

    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    # Policy with cap well above zero spend.
    policy = RemediationPolicy(
        customer_id=customer.id,
        kill_switch_enabled=False,
        max_cost_usd_per_month=100.0,
    )
    db_session.add(policy)
    await db_session.commit()

    run = await svc.create_agent_run(
        db_session,
        scan_id=scan.id,
        llm_connection_id=llm.id,
    )
    assert run.status == AgentRunStatus.pending
