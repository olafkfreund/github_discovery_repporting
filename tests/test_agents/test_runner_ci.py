from __future__ import annotations

"""Unit tests for backend.agents.runner_ci.

Tests cover:
- Happy path dispatch for each platform (GitHub, GitLab, Azure DevOps).
- Auth failure (401) and server error (500) → CIDispatchError.
- Missing ci_workflow_repo on policy → CIDispatchError.
- Unknown platform → CIDispatchError.
- trigger_ci_run task: status transitions pending → running (success path).
- trigger_ci_run task: status → failed when dispatch_workflow raises.

All HTTP calls are intercepted with httpx mock transports — no real network I/O.
All DB interactions use an in-memory SQLite engine created per test.
"""

import asyncio
import json
import secrets
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.agents.runner_ci import CIDispatchError, dispatch_workflow, trigger_ci_run
from backend.models.agent_runs import AgentRun
from backend.models.base import Base
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import AgentRunStatus, AuthType, LLMProviderEnum, Platform, ScanStatus
from backend.models.llm import LLMConnection
from backend.models.remediation_policy import RemediationPolicy
from backend.models.scan import Scan
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Fixtures: per-test isolated in-memory SQLite DB
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ci_engine():
    """Fresh in-memory SQLite engine for CI runner tests."""
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
async def ci_factory(ci_engine):
    """async_sessionmaker bound to the CI test engine."""
    return async_sessionmaker(bind=ci_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def ci_db(ci_factory) -> AsyncSession:
    """Single session for fixture setup helpers."""
    async with ci_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# DB helpers / object factories
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession) -> Customer:
    uid = uuid.uuid4().hex[:8]
    customer = Customer(name=f"CI Corp {uid}", slug=f"cicorp-{uid}")
    db.add(customer)
    await db.flush()
    return customer


async def _make_connection(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    platform: Platform = Platform.github,
    token: str = "ghp_test",
    base_url: str | None = None,
    org_or_group: str = "myorg",
) -> PlatformConnection:
    conn = PlatformConnection(
        customer_id=customer_id,
        platform=platform,
        display_name="Test Connection",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(json.dumps({"token": token})),
        org_or_group=org_or_group,
        base_url=base_url,
        is_active=True,
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


async def _make_run(
    db: AsyncSession,
    scan_id: uuid.UUID,
    llm_id: uuid.UUID,
    *,
    status: AgentRunStatus = AgentRunStatus.pending,
) -> AgentRun:
    run = AgentRun(
        scan_id=scan_id,
        llm_connection_id=llm_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        status=status,
        runtime_mode="ci",
        callback_secret=secrets.token_bytes(32),
    )
    db.add(run)
    await db.flush()
    return run


async def _make_policy(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    ci_workflow_repo: str | None = "myorg/myrepo",
    ci_workflow_ref: str = "main",
) -> RemediationPolicy:
    policy = RemediationPolicy(
        customer_id=customer_id,
        enabled=True,
        runtime_mode="ci",
        ci_workflow_repo=ci_workflow_repo,
        ci_workflow_ref=ci_workflow_ref,
    )
    db.add(policy)
    await db.flush()
    return policy


# ---------------------------------------------------------------------------
# Helpers: build minimal connection/run objects without DB
# ---------------------------------------------------------------------------


def _fake_connection(
    platform: str = "github",
    token: str = "test-token",
    org_or_group: str = "myorg",
    base_url: str | None = None,
) -> MagicMock:
    """Return a lightweight mock that looks like a PlatformConnection."""
    conn = MagicMock()
    conn.platform = platform  # plain string (not enum)
    conn.credentials_encrypted = secrets_service.encrypt(json.dumps({"token": token}))
    conn.org_or_group = org_or_group
    conn.base_url = base_url
    return conn


def _fake_policy(
    ci_workflow_repo: str | None = "myorg/myrepo",
    ci_workflow_ref: str = "main",
) -> MagicMock:
    policy = MagicMock()
    policy.ci_workflow_repo = ci_workflow_repo
    policy.ci_workflow_ref = ci_workflow_ref
    return policy


def _fake_run(callback_secret: bytes | None = None) -> MagicMock:
    run = MagicMock()
    run.id = uuid.uuid4()
    run.callback_secret = callback_secret or secrets.token_bytes(32)
    return run


# ---------------------------------------------------------------------------
# dispatch_workflow — GitHub happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_github_happy_path() -> None:
    """GitHub dispatch succeeds: returns correct platform/dispatch_id/dispatch_url."""
    conn = _fake_connection(platform="github")
    policy = _fake_policy(ci_workflow_repo="acme/infra", ci_workflow_ref="main")
    run = _fake_run()

    # GitHub returns 204 No Content on a successful dispatch.
    transport = httpx.MockTransport(lambda request: httpx.Response(204))

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        result = await dispatch_workflow(
            conn, run, callback_base_url="http://bps.example.com", remediation_policy=policy
        )

    assert result["platform"] == "github"
    assert "acme/infra" in result["dispatch_id"]
    assert "bps-agent.yml" in result["dispatch_id"]
    assert "acme/infra" in result["dispatch_url"]


@pytest.mark.asyncio
async def test_dispatch_github_request_body_shape() -> None:
    """GitHub dispatch sends the correct ref + inputs in the request body."""
    conn = _fake_connection(platform="github")
    policy = _fake_policy(ci_workflow_repo="acme/infra", ci_workflow_ref="develop")
    run = _fake_run()

    captured_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        await dispatch_workflow(
            conn, run, callback_base_url="http://bps.local", remediation_policy=policy
        )

    assert captured_body["ref"] == "develop"
    inputs = captured_body["inputs"]
    assert inputs["agent_run_id"] == str(run.id)
    assert inputs["callback_url"] == "http://bps.local"
    assert "callback_secret_hex" in inputs
    # Verify the hex-encoded secret is correct.
    assert inputs["callback_secret_hex"] == run.callback_secret.hex()


# ---------------------------------------------------------------------------
# dispatch_workflow — GitLab happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_gitlab_happy_path() -> None:
    """GitLab dispatch succeeds: returns correct platform/dispatch_id/dispatch_url."""
    conn = _fake_connection(platform="gitlab", base_url="https://gitlab.com")
    policy = _fake_policy(ci_workflow_repo="99999", ci_workflow_ref="main")
    run = _fake_run()

    pipeline_response = {
        "id": 12345,
        "web_url": "https://gitlab.com/mygroup/myrepo/-/pipelines/12345",
    }

    transport = httpx.MockTransport(lambda request: httpx.Response(201, json=pipeline_response))

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        result = await dispatch_workflow(
            conn, run, callback_base_url="http://bps.example.com", remediation_policy=policy
        )

    assert result["platform"] == "gitlab"
    assert result["dispatch_id"] == "12345"
    assert "pipelines/12345" in result["dispatch_url"]


@pytest.mark.asyncio
async def test_dispatch_gitlab_request_body_shape() -> None:
    """GitLab dispatch sends variables array with correct keys."""
    conn = _fake_connection(platform="gitlab")
    policy = _fake_policy(ci_workflow_repo="12345", ci_workflow_ref="main")
    run = _fake_run()

    captured_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(201, json={"id": 1, "web_url": "http://example.com"})

    transport = httpx.MockTransport(handler)

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        await dispatch_workflow(
            conn, run, callback_base_url="http://bps.local", remediation_policy=policy
        )

    var_keys = {v["key"]: v["value"] for v in captured_body["variables"]}
    assert var_keys["AGENT_RUN_ID"] == str(run.id)
    assert var_keys["CALLBACK_URL"] == "http://bps.local"
    assert "CALLBACK_SECRET_HEX" in var_keys


# ---------------------------------------------------------------------------
# dispatch_workflow — Azure DevOps happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_azure_devops_happy_path() -> None:
    """Azure DevOps dispatch succeeds: returns correct platform/dispatch_id/dispatch_url."""
    conn = _fake_connection(
        platform="azure_devops",
        org_or_group="myazureorg",
        base_url="https://dev.azure.com/myazureorg",
    )
    policy = _fake_policy(ci_workflow_repo="MyProject:42", ci_workflow_ref="main")
    run = _fake_run()

    ado_response = {
        "id": 9999,
        "_links": {
            "web": {
                "href": "https://dev.azure.com/myazureorg/MyProject/_build/results?buildId=9999"
            }
        },
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=ado_response))

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        result = await dispatch_workflow(
            conn, run, callback_base_url="http://bps.example.com", remediation_policy=policy
        )

    assert result["platform"] == "azure_devops"
    assert result["dispatch_id"] == "9999"
    assert "buildId=9999" in result["dispatch_url"]


@pytest.mark.asyncio
async def test_dispatch_azure_devops_request_body_shape() -> None:
    """Azure DevOps dispatch sends variables dict with correct keys and Basic auth."""
    conn = _fake_connection(
        platform="azure_devops",
        token="my-pat",
        org_or_group="myorg",
    )
    policy = _fake_policy(ci_workflow_repo="MyProject:7", ci_workflow_ref="main")
    run = _fake_run()

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={"id": 1, "_links": {}})

    transport = httpx.MockTransport(handler)

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        await dispatch_workflow(
            conn, run, callback_base_url="http://bps.local", remediation_policy=policy
        )

    body = captured["body"]
    variables = body["variables"]
    assert variables["AGENT_RUN_ID"]["value"] == str(run.id)
    assert variables["CALLBACK_URL"]["value"] == "http://bps.local"
    assert "CALLBACK_SECRET_HEX" in variables
    # Verify Basic auth with `:token` pattern.
    assert captured["auth"].startswith("Basic ")


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_github_auth_failure_raises() -> None:
    """GitHub 401 Unauthorized → CIDispatchError."""
    conn = _fake_connection(platform="github")
    policy = _fake_policy()
    run = _fake_run()

    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="Unauthorized"))

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(CIDispatchError, match="401"):
            await dispatch_workflow(
                conn, run, callback_base_url="http://bps.local", remediation_policy=policy
            )


@pytest.mark.asyncio
async def test_dispatch_gitlab_server_error_raises() -> None:
    """GitLab 500 → CIDispatchError."""
    conn = _fake_connection(platform="gitlab")
    policy = _fake_policy(ci_workflow_repo="42")
    run = _fake_run()

    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, text="Internal Server Error")
    )

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(CIDispatchError, match="500"):
            await dispatch_workflow(
                conn, run, callback_base_url="http://bps.local", remediation_policy=policy
            )


@pytest.mark.asyncio
async def test_dispatch_azure_devops_server_error_raises() -> None:
    """Azure DevOps 500 → CIDispatchError."""
    conn = _fake_connection(platform="azure_devops")
    policy = _fake_policy(ci_workflow_repo="MyProject:1")
    run = _fake_run()

    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="error"))

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(CIDispatchError, match="500"):
            await dispatch_workflow(
                conn, run, callback_base_url="http://bps.local", remediation_policy=policy
            )


@pytest.mark.asyncio
async def test_dispatch_unknown_platform_raises() -> None:
    """An unknown platform string → CIDispatchError with clear message."""
    conn = _fake_connection(platform="bitbucket")
    policy = _fake_policy(ci_workflow_repo="myorg/myrepo")
    run = _fake_run()

    with pytest.raises(CIDispatchError, match="bitbucket"):
        await dispatch_workflow(
            conn, run, callback_base_url="http://bps.local", remediation_policy=policy
        )


@pytest.mark.asyncio
async def test_dispatch_missing_ci_workflow_repo_raises() -> None:
    """When ci_workflow_repo is None on the policy → CIDispatchError with clear message."""
    conn = _fake_connection(platform="github")
    policy = _fake_policy(ci_workflow_repo=None)
    run = _fake_run()

    with pytest.raises(CIDispatchError, match="ci_workflow_repo"):
        await dispatch_workflow(
            conn, run, callback_base_url="http://bps.local", remediation_policy=policy
        )


@pytest.mark.asyncio
async def test_dispatch_no_policy_raises() -> None:
    """When remediation_policy is None (unconfigured) → CIDispatchError."""
    conn = _fake_connection(platform="github")
    run = _fake_run()

    with pytest.raises(CIDispatchError, match="ci_workflow_repo"):
        await dispatch_workflow(
            conn, run, callback_base_url="http://bps.local", remediation_policy=None
        )


# ---------------------------------------------------------------------------
# trigger_ci_run — task happy path (status: pending → running)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_ci_run_success_status_transition(
    ci_db: AsyncSession,
    ci_factory: async_sessionmaker,
) -> None:
    """trigger_ci_run schedules a task; on success AgentRun.status → 'running'."""
    customer = await _make_customer(ci_db)
    conn = await _make_connection(ci_db, customer.id, platform=Platform.github)
    llm = await _make_llm(ci_db, customer.id)
    scan = await _make_scan(ci_db, customer.id, conn.id)
    run = await _make_run(ci_db, scan.id, llm.id)
    await _make_policy(ci_db, customer.id, ci_workflow_repo="acme/infra")
    await ci_db.commit()

    dispatch_result = {
        "platform": "github",
        "dispatch_id": "acme/infra:bps-agent.yml@main",
        "dispatch_url": "https://api.github.com/repos/acme/infra/actions/workflows/bps-agent.yml/dispatches",
    }

    with patch(
        "backend.agents.runner_ci.dispatch_workflow",
        new=AsyncMock(return_value=dispatch_result),
    ):
        task = await trigger_ci_run(run, ci_factory)
        assert isinstance(task, asyncio.Task)
        await asyncio.sleep(0.05)  # Let the task run.
        if not task.done():
            await task

    # Verify status updated to running.
    async with ci_factory() as db:
        refreshed = (await db.execute(select(AgentRun).where(AgentRun.id == run.id))).scalar_one()
    assert refreshed.status == AgentRunStatus.running


# ---------------------------------------------------------------------------
# trigger_ci_run — task failure path (dispatch raises → status: failed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_ci_run_dispatch_failure_status_failed(
    ci_db: AsyncSession,
    ci_factory: async_sessionmaker,
) -> None:
    """trigger_ci_run sets AgentRun.status → 'failed' when dispatch_workflow raises."""
    customer = await _make_customer(ci_db)
    conn = await _make_connection(ci_db, customer.id, platform=Platform.github)
    llm = await _make_llm(ci_db, customer.id)
    scan = await _make_scan(ci_db, customer.id, conn.id)
    run = await _make_run(ci_db, scan.id, llm.id)
    await _make_policy(ci_db, customer.id, ci_workflow_repo="acme/infra")
    await ci_db.commit()

    with patch(
        "backend.agents.runner_ci.dispatch_workflow",
        new=AsyncMock(side_effect=CIDispatchError("GitHub 401: Bad credentials")),
    ):
        task = await trigger_ci_run(run, ci_factory)
        await asyncio.sleep(0.05)
        if not task.done():
            await task

    async with ci_factory() as db:
        refreshed = (await db.execute(select(AgentRun).where(AgentRun.id == run.id))).scalar_one()
    assert refreshed.status == AgentRunStatus.failed
    assert "401" in (refreshed.error or "")
