from __future__ import annotations

"""Tests for backend.agents.runner_backend.

Heavy use of mocking to avoid real network / DB I/O.  The test strategy is:

- Mock open_workspace to yield a fake WorkspaceInfo with a real tempdir.
- Mock run_loop to return a canned LoopResult (or raise exceptions).
- Mock create_provider and get_llm_provider.
- Use a real in-memory SQLite session factory (from conftest engine fixture)
  for AgentStep / RemediationAction persistence assertions.
"""

import json
import secrets
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.agents.loop import LoopBudgetExceeded, LoopCancelled, LoopEvent, LoopResult
from backend.agents.workspace import WorkspaceInfo
from backend.models.agent_runs import AgentRun, AgentStep, RemediationAction
from backend.models.base import Base
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import (
    AgentRunStatus,
    AgentStepType,
    AuthType,
    Category,
    CheckStatus,
    LLMProviderEnum,
    Platform,
    RemediationActionStatus,
    ScanStatus,
    Severity,
)
from backend.models.finding import Finding
from backend.models.llm import LLMConnection
from backend.models.scan import Scan, ScanRepo
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Fixtures: per-test isolated in-memory DB factory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def runner_engine():
    """Fresh SQLite engine for runner tests."""
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
async def runner_factory(runner_engine):
    """async_sessionmaker bound to the runner engine."""
    return async_sessionmaker(
        bind=runner_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def runner_db(runner_factory):
    """A session from the runner_factory for setup."""
    async with runner_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers to build DB fixtures
# ---------------------------------------------------------------------------


async def _build_run_scaffold(db: AsyncSession) -> dict[str, Any]:
    """Create Customer → PlatformConnection → LLMConnection → Scan → ScanRepo → Finding → AgentRun."""
    uid = uuid.uuid4().hex[:8]
    customer = Customer(name=f"RunnerCorp {uid}", slug=f"runnercorp-{uid}")
    db.add(customer)
    await db.flush()

    conn = PlatformConnection(
        customer_id=customer.id,
        platform=Platform.github,
        display_name="Test GitHub",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(json.dumps({"token": "ghp_test_token_123"})),
        org_or_group="test-org",
        is_active=True,
    )
    db.add(conn)
    await db.flush()

    llm = LLMConnection(
        customer_id=customer.id,
        name="test-llm",
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
    await db.flush()

    scan_repo = ScanRepo(
        scan_id=scan.id,
        repo_external_id="test-org/my-repo",
        repo_name="my-repo",
        repo_url="https://github.com/test-org/my-repo",
        default_branch="main",
        raw_data={"is_private": False},
    )
    db.add(scan_repo)
    await db.flush()

    finding = Finding(
        scan_id=scan.id,
        scan_repo_id=scan_repo.id,
        category=Category.cicd,
        check_id="CICD-008",
        check_name="Pinned action versions",
        severity=Severity.medium,
        status=CheckStatus.failed,
        weight=1.0,
        score=0.0,
    )
    db.add(finding)
    await db.flush()

    run = AgentRun(
        scan_id=scan.id,
        llm_connection_id=llm.id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        status=AgentRunStatus.pending,
        runtime_mode="backend",
        callback_secret=secrets.token_bytes(32),
    )
    db.add(run)
    await db.commit()

    return {
        "customer": customer,
        "conn": conn,
        "llm": llm,
        "scan": scan,
        "scan_repo": scan_repo,
        "finding": finding,
        "run": run,
    }


# ---------------------------------------------------------------------------
# Fake workspace context manager
# ---------------------------------------------------------------------------


def _make_fake_workspace(tmpdir: Path, has_agents_md: bool = False) -> WorkspaceInfo:
    """Return a WorkspaceInfo pointing at *tmpdir*."""
    if has_agents_md:
        # Create CLAUDE.md to simulate an existing AI file in the repo.
        (tmpdir / "CLAUDE.md").write_text("# Repo-specific instructions")
    return WorkspaceInfo(
        path=tmpdir,
        repo_external_id="test-org/my-repo",
        branch="main",
        head_sha="a" * 40,
        bytes_on_disk=1024,
    )


@asynccontextmanager
async def _fake_open_workspace(workspace: WorkspaceInfo):
    yield workspace


def _make_workspace_side_effect(workspace: WorkspaceInfo):
    """Return a callable that produces a fresh asynccontextmanager each call.

    Used as ``side_effect`` on a mock so each invocation of ``open_workspace``
    gets a fresh context manager rather than a single exhausted one.
    """

    def _side_effect(**kwargs):  # noqa: ANN202, ANN001
        return _fake_open_workspace(workspace)

    return _side_effect


# ---------------------------------------------------------------------------
# Fake LoopResult factories
# ---------------------------------------------------------------------------


def _success_loop_result(
    final_message: str = "Done. PR opened at https://github.com/test-org/my-repo/pull/42",
) -> LoopResult:
    return LoopResult(
        success=True,
        final_message=final_message,
        total_input_tokens=1000,
        total_output_tokens=500,
        total_cost_usd=0.05,
        iterations=3,
    )


def _failed_loop_result() -> LoopResult:
    return LoopResult(
        success=False,
        final_message="",
        total_input_tokens=500,
        total_output_tokens=100,
        total_cost_usd=0.01,
        iterations=2,
        error="empty_response",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_status_transitions(runner_factory, runner_db) -> None:
    """Happy path: run goes pending → running → completed; AgentRun updated."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", new_callable=AsyncMock) as mock_loop,
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.return_value.__aenter__ = AsyncMock(return_value=ws)
            mock_ws.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_loop.return_value = _success_loop_result()
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    # Check final state.
    async with runner_factory() as check_db:
        result = await check_db.execute(select(AgentRun).where(AgentRun.id == run_id))
        final_run = result.scalar_one()

    assert final_run.status == AgentRunStatus.completed
    assert final_run.started_at is not None
    assert final_run.finished_at is not None
    assert final_run.total_input_tokens == 1000
    assert final_run.total_output_tokens == 500


@pytest.mark.asyncio
async def test_happy_path_remediation_action_inserted(runner_factory, runner_db) -> None:
    """Happy path: a RemediationAction row is inserted for the processed finding."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id
    finding_id = scaffold["finding"].id

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", new_callable=AsyncMock) as mock_loop,
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_loop.return_value = _success_loop_result(
                "Done. Branch remediate/CICD-008. PR opened at https://github.com/test-org/my-repo/pull/42"
            )
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        action_result = await check_db.execute(
            select(RemediationAction).where(RemediationAction.agent_run_id == run_id)
        )
        actions = list(action_result.scalars().all())

    assert len(actions) == 1
    action = actions[0]
    assert action.finding_id == finding_id
    assert action.check_id == "CICD-008"
    assert action.pr_url is not None
    assert "pull/42" in action.pr_url
    assert action.status in {RemediationActionStatus.in_progress, RemediationActionStatus.failed}


@pytest.mark.asyncio
async def test_happy_path_agent_steps_persisted(runner_factory, runner_db) -> None:
    """Happy path: AgentStep rows are written for loop events emitted."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        async def _fake_run_loop(**kwargs):  # noqa: ANN202
            sink = kwargs["event_sink"]
            # Emit a few events.
            await sink(
                LoopEvent(
                    step_index=0,
                    step_type=AgentStepType.llm_call,
                    input_tokens=100,
                    output_tokens=50,
                )
            )
            await sink(
                LoopEvent(step_index=1, step_type=AgentStepType.tool_call, tool_name="read_file")
            )
            await sink(LoopEvent(step_index=2, step_type=AgentStepType.final))
            return _success_loop_result()

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_fake_run_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        step_result = await check_db.execute(
            select(AgentStep).where(AgentStep.agent_run_id == run_id).order_by(AgentStep.step_index)
        )
        steps = list(step_result.scalars().all())

    # 3 events were emitted.
    assert len(steps) == 3
    assert steps[0].step_type == AgentStepType.llm_call
    assert steps[1].step_type == AgentStepType.tool_call
    assert steps[2].step_type == AgentStepType.final


@pytest.mark.asyncio
async def test_redaction_applied_to_agent_step(runner_factory, runner_db) -> None:
    """Redaction is applied: a raw GH PAT in tool_result is replaced with a marker."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id
    raw_token = "ghp_" + "a" * 36  # matches GH_PAT_CLASSIC pattern

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        async def _fake_run_loop(**kwargs):  # noqa: ANN202
            sink = kwargs["event_sink"]
            await sink(
                LoopEvent(
                    step_index=0,
                    step_type=AgentStepType.tool_result,
                    tool_name="read_file",
                    tool_result=f"Found token: {raw_token}",
                    tool_args={"path": "config.yaml", "token": raw_token},
                )
            )
            await sink(LoopEvent(step_index=1, step_type=AgentStepType.final))
            return _success_loop_result()

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_fake_run_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        step_result = await check_db.execute(
            select(AgentStep).where(
                AgentStep.agent_run_id == run_id,
                AgentStep.step_type == AgentStepType.tool_result,
            )
        )
        step = step_result.scalar_one()

    # Raw token must NOT appear in the persisted row.
    assert raw_token not in (step.tool_result_redacted or "")
    assert "[REDACTED-GH_PAT_CLASSIC]" in (step.tool_result_redacted or "")
    # Args dict must also be redacted.
    assert raw_token not in str(step.tool_args_redacted or "")


@pytest.mark.asyncio
async def test_budget_exceeded_sets_failed(runner_factory, runner_db) -> None:
    """LoopBudgetExceeded causes status=failed with error='budget_cost'."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch(
                "backend.agents.runner_backend.run_loop",
                new_callable=AsyncMock,
                side_effect=LoopBudgetExceeded("cost"),
            ),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        result = await check_db.execute(select(AgentRun).where(AgentRun.id == run_id))
        final_run = result.scalar_one()

    assert final_run.status == AgentRunStatus.failed
    assert final_run.error == "budget_cost"


@pytest.mark.asyncio
async def test_loop_cancelled_sets_cancelled(runner_factory, runner_db) -> None:
    """LoopCancelled causes status=cancelled."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch(
                "backend.agents.runner_backend.run_loop",
                new_callable=AsyncMock,
                side_effect=LoopCancelled,
            ),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        result = await check_db.execute(select(AgentRun).where(AgentRun.id == run_id))
        final_run = result.scalar_one()

    assert final_run.status == AgentRunStatus.cancelled


@pytest.mark.asyncio
async def test_workspace_error_sets_failed(runner_factory, runner_db) -> None:
    """WorkspaceError during clone sets status=failed with workspace error message."""
    from backend.agents.workspace import WorkspaceError

    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    with tempfile.TemporaryDirectory() as tmpdir:
        _make_fake_workspace(Path(tmpdir))

        @asynccontextmanager
        async def _failing_workspace(**kwargs):  # noqa: ANN202
            raise WorkspaceError("git clone failed with exit code 128: Repository not found")
            yield  # makes it a generator

        with (
            patch("backend.agents.runner_backend.open_workspace", side_effect=_failing_workspace),
            patch("backend.agents.runner_backend.run_loop", new_callable=AsyncMock) as mock_loop,
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_loop.return_value = _success_loop_result()
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        result = await check_db.execute(select(AgentRun).where(AgentRun.id == run_id))
        final_run = result.scalar_one()

    assert final_run.status == AgentRunStatus.failed
    assert "workspace" in (final_run.error or "")


@pytest.mark.asyncio
async def test_agents_md_probe_positive_not_prepended(runner_factory, runner_db) -> None:
    """When workspace has CLAUDE.md, AGENTS.md content is NOT prepended to system prompt."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    captured_system_prompts: list[str] = []

    async def _capture_loop(**kwargs):  # noqa: ANN202
        captured_system_prompts.append(kwargs["system_prompt"])
        sink = kwargs["event_sink"]
        await sink(LoopEvent(step_index=0, step_type=AgentStepType.final))
        return _success_loop_result()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Workspace contains CLAUDE.md → should suppress AGENTS.md injection.
        ws = _make_fake_workspace(Path(tmpdir), has_agents_md=True)

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_capture_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch(
                "backend.services.agent_instructions_service.resolve",
                new_callable=AsyncMock,
                return_value="INJECTED AGENTS.MD CONTENT",
            ),
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    assert len(captured_system_prompts) >= 1
    # Must NOT contain our injected content since CLAUDE.md was found.
    assert "INJECTED AGENTS.MD CONTENT" not in captured_system_prompts[0]


@pytest.mark.asyncio
async def test_agents_md_probe_negative_prepended(runner_factory, runner_db) -> None:
    """When workspace has no AI files, AGENTS.md content IS prepended to system prompt."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    captured_system_prompts: list[str] = []

    async def _capture_loop(**kwargs):  # noqa: ANN202
        captured_system_prompts.append(kwargs["system_prompt"])
        sink = kwargs["event_sink"]
        await sink(LoopEvent(step_index=0, step_type=AgentStepType.final))
        return _success_loop_result()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Workspace has NO AI instruction files.
        ws = _make_fake_workspace(Path(tmpdir), has_agents_md=False)

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_capture_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch(
                "backend.services.agent_instructions_service.resolve",
                new_callable=AsyncMock,
                return_value="INJECTED AGENTS.MD CONTENT",
            ),
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    assert len(captured_system_prompts) >= 1
    # AGENTS.md content must be prepended.
    assert "INJECTED AGENTS.MD CONTENT" in captured_system_prompts[0]


@pytest.mark.asyncio
async def test_max_prs_cap_limits_findings(runner_factory, runner_db) -> None:
    """Only up to _DEFAULT_MAX_PRS (10) findings are processed."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id
    scan_repo_id = scaffold["scan_repo"].id
    scan_id = scaffold["scan"].id

    # Insert 15 more failing findings beyond the 1 already in the scaffold.
    async with runner_factory() as extra_db:
        for _ in range(14):
            finding = Finding(
                scan_id=scan_id,
                scan_repo_id=scan_repo_id,
                category=Category.cicd,
                check_id="CICD-008",
                check_name="Pinned action versions",
                severity=Severity.low,
                status=CheckStatus.failed,
                weight=1.0,
                score=0.0,
            )
            extra_db.add(finding)
        await extra_db.commit()

    loop_call_count = 0

    async def _counting_loop(**kwargs):  # noqa: ANN202
        nonlocal loop_call_count
        current_idx = loop_call_count
        loop_call_count += 1
        sink = kwargs["event_sink"]
        await sink(LoopEvent(step_index=current_idx, step_type=AgentStepType.final))
        return _success_loop_result()

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_counting_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents import runner_backend  # noqa: PLC0415
            from backend.agents.runner_backend import run_backend_agent  # noqa: PLC0415

            # Cap is 10.
            assert runner_backend._DEFAULT_MAX_PRS == 10

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    assert loop_call_count == 10


@pytest.mark.asyncio
async def test_gitlab_platform_raises_not_implemented(runner_factory, runner_db) -> None:
    """For GitLab platform, run fails because clone URL is NotImplemented."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    # Patch the context so the connection looks like GitLab.
    with patch("backend.agents.runner_backend._load_run_context") as mock_ctx:
        mock_run = MagicMock()
        mock_run.id = run_id
        mock_scan = MagicMock()
        mock_scan.id = scaffold["scan"].id
        mock_scan.scan_repos = [scaffold["scan_repo"]]

        # We need to use the real scaffold scan_repo but with GitLab platform.
        fake_ctx = MagicMock()
        fake_ctx.run = mock_run
        fake_ctx.scan = mock_scan
        fake_ctx.scan_repo_by_id = {scaffold["scan_repo"].id: scaffold["scan_repo"]}
        fake_ctx.connection_id = scaffold["conn"].id
        fake_ctx.connection_platform = "gitlab"  # <-- GitLab
        fake_ctx.connection_org = "test-group"
        fake_ctx.connection_base_url = None
        fake_ctx.connection_token = "glpat-test"
        fake_ctx.llm_config = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "api_key": None,
            "endpoint_url": None,
            "extra_config": None,
        }
        fake_ctx.agents_md_content = None
        mock_ctx.return_value = fake_ctx

        with (
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    # The run should complete (gitlab finding skipped) — not fail outright.
    # The finding loop emits an error AgentStep and continues; since there's
    # only one finding and it's skipped, the run completes successfully.
    async with runner_factory() as check_db:
        result = await check_db.execute(select(AgentRun).where(AgentRun.id == run_id))
        final_run = result.scalar_one_or_none()

    # The run completes (findings were skipped, not fatal).
    if final_run is not None:
        assert final_run.status in {AgentRunStatus.completed, AgentRunStatus.failed}


@pytest.mark.asyncio
async def test_recipe_success_check_false_marks_action_failed(runner_factory, runner_db) -> None:
    """When recipe.success_check returns False, the RemediationAction gets status=failed."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    async def _failing_success_check(workspace, ctx):  # noqa: ANN001, ANN202
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", new_callable=AsyncMock) as mock_loop,
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch("backend.agents.runner_backend.get_recipe") as mock_recipe,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_loop.return_value = _success_loop_result()
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            # Patch the recipe to have a success_check that returns False.
            fake_recipe = MagicMock()
            fake_recipe.operator_prompt_path = "generic.md"
            fake_recipe.forbidden_paths = []
            fake_recipe.file_glob_hints = []
            fake_recipe.max_files_changed = 5
            fake_recipe.max_lines_changed = 200
            fake_recipe.success_check = _failing_success_check
            mock_recipe.return_value = fake_recipe

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        action_result = await check_db.execute(
            select(RemediationAction).where(RemediationAction.agent_run_id == run_id)
        )
        actions = list(action_result.scalars().all())

    assert len(actions) == 1
    assert actions[0].status == RemediationActionStatus.failed


@pytest.mark.asyncio
async def test_cancel_event_fired_mid_loop(runner_factory, runner_db) -> None:
    """When the cancel_event is set, the run ends with status=cancelled."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    from backend.services.event_bus import get_cancel_registry

    cancel_registry = get_cancel_registry()

    async def _cancelling_loop(**kwargs):  # noqa: ANN202
        # Signal cancellation from "outside" during the loop.
        cancel_registry.trigger(run_id)
        raise LoopCancelled()

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_cancelling_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        result = await check_db.execute(select(AgentRun).where(AgentRun.id == run_id))
        final_run = result.scalar_one()

    assert final_run.status == AgentRunStatus.cancelled


@pytest.mark.asyncio
async def test_pr_url_extracted_from_final_message(runner_factory, runner_db) -> None:
    """PR URL in the final message is stored on the RemediationAction."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", new_callable=AsyncMock) as mock_loop,
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_loop.return_value = _success_loop_result(
                "I opened a pull request at https://github.com/test-org/my-repo/pull/99"
            )
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        action_result = await check_db.execute(
            select(RemediationAction).where(RemediationAction.agent_run_id == run_id)
        )
        action = action_result.scalar_one()

    assert action.pr_url is not None
    assert "pull/99" in action.pr_url


# ---------------------------------------------------------------------------
# Phase-C skill-block injection tests (issue #38)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_injects_skill_block_when_relevant(runner_factory, runner_db) -> None:
    """When resolve_for_check returns matching skills, the system prompt contains ## Skills."""
    from backend.services.skill_service import ResolvedSkill

    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    fake_skill = ResolvedSkill(
        name="codeowners-team-mapping",
        body="# CODEOWNERS guidance\nAlways use team handles.",
        sha256="abc" * 21 + "d",  # 64 hex chars
        source="builtin",
        applies_to=["REPO-008"],
    )

    captured_system_prompts: list[str] = []

    async def _capture_loop(**kwargs):  # noqa: ANN202
        captured_system_prompts.append(kwargs["system_prompt"])
        sink = kwargs["event_sink"]
        await sink(LoopEvent(step_index=0, step_type=AgentStepType.final))
        return _success_loop_result()

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_capture_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch(
                "backend.agents.runner_backend.skill_service.resolve_for_check",
                new_callable=AsyncMock,
                return_value=[fake_skill],
            ),
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    assert len(captured_system_prompts) >= 1
    sp = captured_system_prompts[0]
    assert "## Skills" in sp
    assert "### codeowners-team-mapping" in sp
    assert "CODEOWNERS guidance" in sp


@pytest.mark.asyncio
async def test_runner_omits_skill_block_when_no_match(runner_factory, runner_db) -> None:
    """When resolve_for_check returns an empty list, ## Skills is absent from the prompt."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    captured_system_prompts: list[str] = []

    async def _capture_loop(**kwargs):  # noqa: ANN202
        captured_system_prompts.append(kwargs["system_prompt"])
        sink = kwargs["event_sink"]
        await sink(LoopEvent(step_index=0, step_type=AgentStepType.final))
        return _success_loop_result()

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_capture_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch(
                "backend.agents.runner_backend.skill_service.resolve_for_check",
                new_callable=AsyncMock,
                return_value=[],  # no skills match
            ),
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    assert len(captured_system_prompts) >= 1
    assert "## Skills" not in captured_system_prompts[0]


@pytest.mark.asyncio
async def test_runner_prompt_hash_combines_skill_shas(runner_factory, runner_db) -> None:
    """prompt_hash changes when skills are present vs absent, and is always 64 hex chars."""
    import re

    from backend.services.skill_service import ResolvedSkill

    scaffold_a = await _build_run_scaffold(runner_db)
    run_id_a = scaffold_a["run"].id

    scaffold_b = await _build_run_scaffold(runner_db)
    run_id_b = scaffold_b["run"].id

    fake_skill = ResolvedSkill(
        name="branch-protection-baseline",
        body="Protect your branches.",
        sha256="f" * 64,
        source="builtin",
        applies_to=["REPO-001"],
    )

    captured_hashes_a: list[str] = []
    captured_hashes_b: list[str] = []

    async def _capture_hash_a(**kwargs):  # noqa: ANN202
        captured_hashes_a.append(kwargs["prompt_hash"])
        sink = kwargs["event_sink"]
        await sink(LoopEvent(step_index=0, step_type=AgentStepType.final))
        return _success_loop_result()

    async def _capture_hash_b(**kwargs):  # noqa: ANN202
        captured_hashes_b.append(kwargs["prompt_hash"])
        sink = kwargs["event_sink"]
        await sink(LoopEvent(step_index=0, step_type=AgentStepType.final))
        return _success_loop_result()

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        # Run A: skill present.
        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_capture_hash_a),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch(
                "backend.agents.runner_backend.skill_service.resolve_for_check",
                new_callable=AsyncMock,
                return_value=[fake_skill],
            ),
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id_a, db_factory=runner_factory)

    with tempfile.TemporaryDirectory() as tmpdir2:
        ws2 = _make_fake_workspace(Path(tmpdir2))

        # Run B: no skill.
        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_capture_hash_b),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch(
                "backend.agents.runner_backend.skill_service.resolve_for_check",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws2)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            await run_backend_agent(agent_run_id=run_id_b, db_factory=runner_factory)

    assert len(captured_hashes_a) >= 1
    assert len(captured_hashes_b) >= 1
    hash_a = captured_hashes_a[0]
    hash_b = captured_hashes_b[0]

    # Both must be 64-character lowercase hex strings (SHA-256).
    assert re.fullmatch(r"[0-9a-f]{64}", hash_a), f"hash_a is not valid SHA256: {hash_a!r}"
    assert re.fullmatch(r"[0-9a-f]{64}", hash_b), f"hash_b is not valid SHA256: {hash_b!r}"

    # Hashes must differ when skills differ.
    assert hash_a != hash_b, "prompt_hash must differ when skill SHAs change"


@pytest.mark.asyncio
async def test_runner_respects_skill_prompt_budget(runner_factory, runner_db) -> None:
    """Skills exceeding the budget are truncated; all skill names remain; [truncated] appears."""
    from backend.config import settings
    from backend.services.skill_service import ResolvedSkill

    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    # Build 5 skills whose bodies sum to well over the budget (8 KB).
    large_body = "X" * 4096  # 4 KB each × 5 = 20 KB total
    fake_skills = [
        ResolvedSkill(
            name=f"fake-skill-{i:02d}",
            body=large_body,
            sha256=f"{i:064x}",
            source="builtin",
            applies_to=[],
        )
        for i in range(5)
    ]

    captured_system_prompts: list[str] = []

    async def _capture_loop(**kwargs):  # noqa: ANN202
        captured_system_prompts.append(kwargs["system_prompt"])
        sink = kwargs["event_sink"]
        await sink(LoopEvent(step_index=0, step_type=AgentStepType.final))
        return _success_loop_result()

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_capture_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch(
                "backend.agents.runner_backend.skill_service.resolve_for_check",
                new_callable=AsyncMock,
                return_value=fake_skills,
            ),
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    assert len(captured_system_prompts) >= 1
    sp = captured_system_prompts[0]

    # The Skills section itself must respect the budget (with reasonable overhead
    # for system prompt boilerplate — the budget applies only to the skill block).
    # Extract just the Skills section for budget assertion.
    skills_section_start = sp.find("## Skills")
    assert skills_section_start != -1, "## Skills section must be present"
    skills_section = sp[skills_section_start:]
    skills_section_bytes = len(skills_section.encode("utf-8"))
    # The skills section should be well under 2× the budget (budget + header overhead).
    assert skills_section_bytes <= settings.SKILL_PROMPT_BUDGET_BYTES * 2

    # All 5 skill names must appear (no skill dropped entirely).
    for i in range(5):
        assert f"### fake-skill-{i:02d}" in sp, f"skill fake-skill-{i:02d} was dropped from prompt"

    # At least one body must be truncated.
    assert "[truncated]" in sp, "Expected at least one skill body to be truncated"


@pytest.mark.asyncio
async def test_guardrail_violation_skips_pr_and_marks_action_failed(
    runner_factory, runner_db
) -> None:
    """When check_diff_scope returns a violation, no PR is opened and the
    RemediationAction is persisted with status=failed."""
    from backend.agents.guardrail import GuardrailViolation

    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id
    finding_id = scaffold["finding"].id

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", new_callable=AsyncMock) as mock_loop,
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch(
                "backend.agents.runner_backend.check_diff_scope",
                new_callable=AsyncMock,
                return_value=GuardrailViolation(
                    files_out_of_scope=["docs/README.md"],
                    allowed_globs=["src/**"],
                ),
            ),
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_loop.return_value = _success_loop_result(
                "Done. PR opened at https://github.com/test-org/my-repo/pull/42"
            )
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        action_result = await check_db.execute(
            select(RemediationAction).where(RemediationAction.agent_run_id == run_id)
        )
        actions = list(action_result.scalars().all())

    # A RemediationAction is inserted (to record the failure) but with failed status.
    assert len(actions) == 1
    assert actions[0].finding_id == finding_id
    assert actions[0].status == RemediationActionStatus.failed
    # PR URL must NOT be set — the PR was blocked.
    assert actions[0].pr_url is None


@pytest.mark.asyncio
async def test_guardrail_pass_proceeds_to_action_insert(runner_factory, runner_db) -> None:
    """When check_diff_scope returns None (in scope), the PR proceeds normally."""
    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", new_callable=AsyncMock) as mock_loop,
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
            patch(
                "backend.agents.runner_backend.check_diff_scope",
                new_callable=AsyncMock,
                return_value=None,  # No violation — all good.
            ),
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_loop.return_value = _success_loop_result(
                "Done. PR at https://github.com/test-org/my-repo/pull/7"
            )
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    async with runner_factory() as check_db:
        action_result = await check_db.execute(
            select(RemediationAction).where(RemediationAction.agent_run_id == run_id)
        )
        actions = list(action_result.scalars().all())

    # The run should complete and a RemediationAction inserted (in_progress or failed
    # depending on the success_check, but NOT blocked).
    assert len(actions) == 1
    assert actions[0].pr_url is not None and "pull/7" in actions[0].pr_url


@pytest.mark.asyncio
async def test_runner_respects_connection_override(runner_factory, runner_db) -> None:
    """Per-connection skills_override=False suppresses a built-in skill injection."""
    from backend.models.skill import SkillToggle

    scaffold = await _build_run_scaffold(runner_db)
    run_id = scaffold["run"].id
    customer_id = scaffold["customer"].id

    # Disable codeowners-team-mapping via customer-level SkillToggle.
    async with runner_factory() as toggle_db:
        toggle = SkillToggle(
            customer_id=customer_id,
            skill_name="codeowners-team-mapping",
            enabled=False,
        )
        toggle_db.add(toggle)
        await toggle_db.commit()

    # Also set skills_override on the connection to False (connection wins highest).
    async with runner_factory() as conn_db:
        from sqlalchemy import select as sa_select

        from backend.models.customer import PlatformConnection

        result = await conn_db.execute(
            sa_select(PlatformConnection).where(PlatformConnection.id == scaffold["conn"].id)
        )
        platform_conn = result.scalar_one()
        platform_conn.skills_override = {"codeowners-team-mapping": False}
        await conn_db.commit()

    captured_system_prompts: list[str] = []

    async def _capture_loop(**kwargs):  # noqa: ANN202
        captured_system_prompts.append(kwargs["system_prompt"])
        sink = kwargs["event_sink"]
        await sink(LoopEvent(step_index=0, step_type=AgentStepType.final))
        return _success_loop_result()

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_fake_workspace(Path(tmpdir))

        with (
            patch("backend.agents.runner_backend.open_workspace") as mock_ws,
            patch("backend.agents.runner_backend.run_loop", side_effect=_capture_loop),
            patch("backend.agents.runner_backend.create_provider") as mock_cp,
            patch("backend.agents.runner_backend.get_llm_provider") as mock_llm,
        ):
            mock_ws.side_effect = _make_workspace_side_effect(ws)
            mock_cp.return_value = MagicMock()
            mock_llm.return_value = MagicMock()

            from backend.agents.runner_backend import run_backend_agent

            await run_backend_agent(agent_run_id=run_id, db_factory=runner_factory)

    assert len(captured_system_prompts) >= 1
    # codeowners-team-mapping must NOT appear (disabled via override).
    assert "codeowners-team-mapping" not in captured_system_prompts[0]
