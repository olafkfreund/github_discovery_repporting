"""Tests for backend.services.scan_service — auto-dispatch hook.

Tests the ``_maybe_dispatch_agent_run`` behaviour added for issue #32,
updated for issue #43 which materialises the ``RemediationPolicy`` model.

Strategy:
  - Use an in-memory SQLite engine (mirrors conftest.py pattern) for setup.
  - Insert real ``RemediationPolicy`` rows linked to the customer under test.
  - Mock ``agent_service.create_agent_run`` and ``trigger_backend_run`` to avoid
    real DB/background-task side-effects.
  - Patch ``backend.database.AsyncSessionLocal`` via ``backend.database`` module
    (the local import target used inside ``_maybe_dispatch_agent_run``).
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models.base import Base
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import (
    AgentRunStatus,
    AuthType,
    LLMProviderEnum,
    Platform,
    ScanStatus,
)
from backend.models.llm import LLMConnection
from backend.models.remediation_policy import RemediationPolicy
from backend.models.scan import Scan
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Fixtures: isolated in-memory SQLite engine per test
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def scan_svc_engine():
    """Fresh SQLite engine for scan_service tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    engine.dialect.native_uuid = False  # type: ignore[attr-defined]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def scan_svc_factory(scan_svc_engine):
    """async_sessionmaker bound to the scan_svc engine."""
    return async_sessionmaker(
        bind=scan_svc_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def scan_svc_db(scan_svc_factory):
    """A session from the scan_svc_factory for test setup."""
    async with scan_svc_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# DB scaffold helpers
# ---------------------------------------------------------------------------


async def _build_scan_scaffold(db: AsyncSession) -> dict:
    """Create Customer → PlatformConnection → LLMConnection → Scan (completed)."""
    uid = uuid.uuid4().hex[:8]
    customer = Customer(name=f"DispatchCorp {uid}", slug=f"dispatchcorp-{uid}")
    db.add(customer)
    await db.flush()

    conn = PlatformConnection(
        customer_id=customer.id,
        platform=Platform.github,
        display_name="GitHub Conn",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(json.dumps({"token": "ghp_test"})),
        org_or_group="test-org",
        is_active=True,
    )
    db.add(conn)
    await db.flush()

    llm = LLMConnection(
        customer_id=customer.id,
        name="default-llm",
        provider=LLMProviderEnum.anthropic,
        model="claude-sonnet-4-6",
        is_default=True,
    )
    db.add(llm)
    await db.flush()

    scan = Scan(
        customer_id=customer.id,
        connection_id=conn.id,
        status=ScanStatus.completed,
    )
    db.add(scan)
    await db.commit()

    return {"customer": customer, "conn": conn, "llm": llm, "scan": scan}


async def _add_policy(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    auto_dispatch: bool,
    kill_switch_enabled: bool = False,
) -> RemediationPolicy:
    """Insert a RemediationPolicy row for the given customer and commit."""
    policy = RemediationPolicy(
        customer_id=customer_id,
        auto_dispatch=auto_dispatch,
        kill_switch_enabled=kill_switch_enabled,
    )
    db.add(policy)
    await db.commit()
    return policy


# ---------------------------------------------------------------------------
# Helper: async session context manager shim
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _fake_session_ctx(session: AsyncSession):
    """Yield *session* as an async context manager."""
    yield session


# ---------------------------------------------------------------------------
# Tests: _maybe_dispatch_agent_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_remediation_policy_no_dispatch(scan_svc_db) -> None:
    """Customer with no RemediationPolicy row → no AgentRun created.

    When ``customer.remediation_policy`` is ``None``, both ``auto_dispatch``
    and ``kill_switch_enabled`` evaluate to ``False``.
    """
    from backend.services.scan_service import _maybe_dispatch_agent_run

    scaffold = await _build_scan_scaffold(scan_svc_db)
    scan = scaffold["scan"]
    customer = scaffold["customer"]
    # No RemediationPolicy row inserted — customer.remediation_policy is None.

    with (
        patch.object(scan_svc_db, "get", AsyncMock(return_value=customer)),
        patch("backend.services.scan_service.agent_service") as mock_svc,
    ):
        await _maybe_dispatch_agent_run(scan_svc_db, scan)

    mock_svc.create_agent_run.assert_not_called()
    mock_svc.trigger_backend_run.assert_not_called()


@pytest.mark.asyncio
async def test_auto_dispatch_false_no_dispatch(scan_svc_db) -> None:
    """Customer.remediation_policy.auto_dispatch=False → no AgentRun created."""
    from backend.services.scan_service import _maybe_dispatch_agent_run

    scaffold = await _build_scan_scaffold(scan_svc_db)
    scan = scaffold["scan"]
    customer = scaffold["customer"]
    await _add_policy(scan_svc_db, customer.id, auto_dispatch=False)
    # Reload customer so the selectin relationship is populated.
    await scan_svc_db.refresh(customer)

    with (
        patch.object(scan_svc_db, "get", AsyncMock(return_value=customer)),
        patch("backend.services.scan_service.agent_service") as mock_svc,
    ):
        await _maybe_dispatch_agent_run(scan_svc_db, scan)

    mock_svc.create_agent_run.assert_not_called()
    mock_svc.trigger_backend_run.assert_not_called()


@pytest.mark.asyncio
async def test_auto_dispatch_true_kill_switch_off_dispatches(scan_svc_db) -> None:
    """auto_dispatch=True + kill_switch=False + LLMConnection → AgentRun created and triggered."""
    from backend.services.scan_service import _maybe_dispatch_agent_run

    scaffold = await _build_scan_scaffold(scan_svc_db)
    scan = scaffold["scan"]
    customer = scaffold["customer"]
    await _add_policy(scan_svc_db, customer.id, auto_dispatch=True, kill_switch_enabled=False)
    await scan_svc_db.refresh(customer)

    fake_run = MagicMock()
    fake_run.id = uuid.uuid4()
    fake_run.status = AgentRunStatus.pending

    with (
        patch.object(scan_svc_db, "get", AsyncMock(return_value=customer)),
        patch("backend.services.scan_service.agent_service") as mock_svc,
        patch(
            "backend.database.AsyncSessionLocal",
            return_value=_fake_session_ctx(scan_svc_db),
        ),
    ):
        mock_svc.create_agent_run = AsyncMock(return_value=fake_run)
        mock_svc.trigger_backend_run = AsyncMock()

        await _maybe_dispatch_agent_run(scan_svc_db, scan)

    # create_agent_run must have been called with our scan_id.
    mock_svc.create_agent_run.assert_called_once()
    call_kwargs = mock_svc.create_agent_run.call_args.kwargs
    assert call_kwargs.get("scan_id") == scan.id

    # trigger_backend_run must have been called with the returned run.
    mock_svc.trigger_backend_run.assert_called_once()
    assert mock_svc.trigger_backend_run.call_args.args[0] is fake_run


@pytest.mark.asyncio
async def test_auto_dispatch_true_kill_switch_active_no_dispatch(scan_svc_db) -> None:
    """auto_dispatch=True but kill_switch=True → no AgentRun, log message."""
    from backend.services.scan_service import _maybe_dispatch_agent_run

    scaffold = await _build_scan_scaffold(scan_svc_db)
    scan = scaffold["scan"]
    customer = scaffold["customer"]
    await _add_policy(scan_svc_db, customer.id, auto_dispatch=True, kill_switch_enabled=True)
    await scan_svc_db.refresh(customer)

    with (
        patch.object(scan_svc_db, "get", AsyncMock(return_value=customer)),
        patch("backend.services.scan_service.agent_service") as mock_svc,
    ):
        await _maybe_dispatch_agent_run(scan_svc_db, scan)

    mock_svc.create_agent_run.assert_not_called()
    mock_svc.trigger_backend_run.assert_not_called()


@pytest.mark.asyncio
async def test_auto_dispatch_no_llm_connection_no_dispatch(scan_svc_db) -> None:
    """auto_dispatch=True but customer has no LLMConnection → no AgentRun, warning logged."""
    from sqlalchemy import delete

    from backend.models.llm import LLMConnection as LLMConn
    from backend.services.scan_service import _maybe_dispatch_agent_run

    scaffold = await _build_scan_scaffold(scan_svc_db)
    scan = scaffold["scan"]
    customer = scaffold["customer"]
    await _add_policy(scan_svc_db, customer.id, auto_dispatch=True, kill_switch_enabled=False)
    await scan_svc_db.refresh(customer)

    # Remove the LLM connection so the lookup finds nothing.
    await scan_svc_db.execute(delete(LLMConn).where(LLMConn.customer_id == customer.id))
    await scan_svc_db.commit()

    with (
        patch.object(scan_svc_db, "get", AsyncMock(return_value=customer)),
        patch("backend.services.scan_service.agent_service") as mock_svc,
    ):
        await _maybe_dispatch_agent_run(scan_svc_db, scan)

    mock_svc.create_agent_run.assert_not_called()


@pytest.mark.asyncio
async def test_auto_dispatch_create_raises_exception_does_not_propagate(scan_svc_db) -> None:
    """When create_agent_run raises, the exception is swallowed; no re-raise."""
    from backend.services.scan_service import _maybe_dispatch_agent_run

    scaffold = await _build_scan_scaffold(scan_svc_db)
    scan = scaffold["scan"]
    customer = scaffold["customer"]
    await _add_policy(scan_svc_db, customer.id, auto_dispatch=True, kill_switch_enabled=False)
    await scan_svc_db.refresh(customer)

    with (
        patch.object(scan_svc_db, "get", AsyncMock(return_value=customer)),
        patch("backend.services.scan_service.agent_service") as mock_svc,
        patch(
            "backend.database.AsyncSessionLocal",
            return_value=_fake_session_ctx(scan_svc_db),
        ),
    ):
        mock_svc.create_agent_run = AsyncMock(side_effect=RuntimeError("DB exploded"))
        mock_svc.trigger_backend_run = AsyncMock()

        # Must NOT raise — the function swallows all exceptions.
        await _maybe_dispatch_agent_run(scan_svc_db, scan)

    # trigger_backend_run must NOT have been called since create raised.
    mock_svc.trigger_backend_run.assert_not_called()

    # Scan still in completed state — the exception didn't roll back the scan row.
    assert scan.status == ScanStatus.completed
