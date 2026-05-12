from __future__ import annotations

"""Tests for AgentRun, AgentStep, and RemediationAction SQLAlchemy models."""

import secrets
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun, AgentStep, RemediationAction
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import (
    AgentRunStatus,
    AgentStepType,
    AuthType,
    LLMProviderEnum,
    Platform,
    RemediationActionStatus,
    ScanStatus,
)
from backend.models.finding import Finding
from backend.models.llm import LLMConnection
from backend.models.scan import Scan

# ---------------------------------------------------------------------------
# Test helpers / factories
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, *, suffix: str = "") -> Customer:
    """Create and persist a minimal Customer."""
    uid = uuid.uuid4().hex[:8]
    customer = Customer(name=f"Test Corp {uid}{suffix}", slug=f"test-corp-{uid}{suffix}")
    db.add(customer)
    await db.flush()
    return customer


async def _make_connection(db: AsyncSession, customer_id: uuid.UUID) -> PlatformConnection:
    """Create and persist a minimal PlatformConnection."""
    conn = PlatformConnection(
        customer_id=customer_id,
        platform=Platform.github,
        display_name="Test GitHub",
        auth_type=AuthType.token,
        credentials_encrypted=b"placeholder",
        org_or_group="test-org",
        is_active=True,
    )
    db.add(conn)
    await db.flush()
    return conn


async def _make_llm_connection(
    db: AsyncSession, customer_id: uuid.UUID, *, name: str = "Test LLM"
) -> LLMConnection:
    """Create and persist a minimal LLMConnection."""
    llm = LLMConnection(
        customer_id=customer_id,
        name=name,
        provider=LLMProviderEnum.anthropic,
        model="claude-3-5-sonnet-20241022",
    )
    db.add(llm)
    await db.flush()
    return llm


async def _make_scan(db: AsyncSession, customer_id: uuid.UUID, connection_id: uuid.UUID) -> Scan:
    """Create and persist a minimal Scan."""
    scan = Scan(
        customer_id=customer_id,
        connection_id=connection_id,
        status=ScanStatus.completed,
    )
    db.add(scan)
    await db.flush()
    return scan


async def _make_finding(db: AsyncSession, scan_id: uuid.UUID) -> Finding:
    """Create and persist a minimal Finding."""
    from backend.models.enums import Category, CheckStatus, Severity

    finding = Finding(
        scan_id=scan_id,
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
    return finding


async def _make_agent_run(
    db: AsyncSession,
    scan_id: uuid.UUID,
    llm_connection_id: uuid.UUID,
    *,
    status: AgentRunStatus = AgentRunStatus.pending,
    runtime_mode: str = "backend",
) -> AgentRun:
    """Create and persist a minimal AgentRun."""
    run = AgentRun(
        scan_id=scan_id,
        llm_connection_id=llm_connection_id,
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        status=status,
        runtime_mode=runtime_mode,
        callback_secret=secrets.token_bytes(32),
    )
    db.add(run)
    await db.flush()
    return run


async def _make_agent_step(
    db: AsyncSession,
    agent_run_id: uuid.UUID,
    *,
    step_index: int = 0,
    step_type: AgentStepType = AgentStepType.llm_call,
) -> AgentStep:
    """Create and persist a minimal AgentStep."""
    step = AgentStep(
        agent_run_id=agent_run_id,
        step_index=step_index,
        step_type=step_type,
        input_tokens=100,
        output_tokens=50,
        latency_ms=1200,
        status="ok",
    )
    db.add(step)
    await db.flush()
    return step


async def _make_remediation_action(
    db: AsyncSession,
    agent_run_id: uuid.UUID,
    finding_id: uuid.UUID,
    *,
    status: RemediationActionStatus = RemediationActionStatus.planned,
) -> RemediationAction:
    """Create and persist a minimal RemediationAction."""
    action = RemediationAction(
        agent_run_id=agent_run_id,
        finding_id=finding_id,
        check_id="CICD-008",
        status=status,
    )
    db.add(action)
    await db.flush()
    return action


# ---------------------------------------------------------------------------
# Fixture: fully wired scaffold used by multiple tests
# ---------------------------------------------------------------------------


async def _build_scaffold(db: AsyncSession) -> dict:
    """Return a dict with customer, llm, scan, finding, run, step, action."""
    customer = await _make_customer(db)
    conn = await _make_connection(db, customer.id)
    llm = await _make_llm_connection(db, customer.id)
    scan = await _make_scan(db, customer.id, conn.id)
    finding = await _make_finding(db, scan.id)
    run = await _make_agent_run(db, scan.id, llm.id)
    step = await _make_agent_step(db, run.id)
    action = await _make_remediation_action(db, run.id, finding.id)
    return {
        "customer": customer,
        "llm": llm,
        "scan": scan,
        "finding": finding,
        "run": run,
        "step": step,
        "action": action,
    }


# ---------------------------------------------------------------------------
# Creation and default values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_run_create_defaults(db_session: AsyncSession) -> None:
    """A freshly created AgentRun has correct defaults."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id)

    assert run.id is not None
    assert run.status == AgentRunStatus.pending
    assert run.total_input_tokens == 0
    assert run.total_output_tokens == 0
    assert run.total_cost_usd == 0.0
    assert run.runtime_mode == "backend"
    assert len(run.callback_secret) == 32
    assert run.error is None
    assert run.started_at is None
    assert run.finished_at is None


@pytest.mark.asyncio
async def test_agent_step_create(db_session: AsyncSession) -> None:
    """An AgentStep persists with all required fields."""
    s = await _build_scaffold(db_session)
    step = s["step"]

    assert step.id is not None
    assert step.agent_run_id == s["run"].id
    assert step.step_index == 0
    assert step.step_type == AgentStepType.llm_call
    assert step.input_tokens == 100
    assert step.output_tokens == 50
    assert step.latency_ms == 1200
    assert step.status == "ok"


@pytest.mark.asyncio
async def test_remediation_action_create(db_session: AsyncSession) -> None:
    """A RemediationAction persists with correct defaults."""
    s = await _build_scaffold(db_session)
    action = s["action"]

    assert action.id is not None
    assert action.agent_run_id == s["run"].id
    assert action.finding_id == s["finding"].id
    assert action.check_id == "CICD-008"
    assert action.status == RemediationActionStatus.planned
    assert action.pr_url is None
    assert action.branch is None
    assert action.opened_at is None
    assert action.merged_at is None


# ---------------------------------------------------------------------------
# Relationship loading (explicit queries only — avoids MissingGreenlet)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relationships_load_correctly(db_session: AsyncSession) -> None:
    """AgentRun relationships load steps and actions via explicit queries."""
    s = await _build_scaffold(db_session)
    run_id = s["run"].id

    # Reload to confirm run exists
    await db_session.execute(select(AgentRun).where(AgentRun.id == run_id))

    # Load steps explicitly
    steps_result = await db_session.execute(
        select(AgentStep).where(AgentStep.agent_run_id == run_id)
    )
    steps = steps_result.scalars().all()
    assert len(steps) == 1
    assert steps[0].step_index == 0

    # Load actions explicitly
    actions_result = await db_session.execute(
        select(RemediationAction).where(RemediationAction.agent_run_id == run_id)
    )
    actions = actions_result.scalars().all()
    assert len(actions) == 1
    assert actions[0].check_id == "CICD-008"


@pytest.mark.asyncio
async def test_remediation_action_finding_relationship(db_session: AsyncSession) -> None:
    """RemediationAction.finding_id correctly points to the Finding row."""
    s = await _build_scaffold(db_session)

    result = await db_session.execute(
        select(RemediationAction).where(RemediationAction.id == s["action"].id)
    )
    action = result.scalar_one()
    assert action.finding_id == s["finding"].id


# ---------------------------------------------------------------------------
# UniqueConstraint on (agent_run_id, step_index)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unique_constraint_step_index(db_session: AsyncSession) -> None:
    """Inserting two steps with the same index on one run raises IntegrityError."""
    s = await _build_scaffold(db_session)

    duplicate_step = AgentStep(
        agent_run_id=s["run"].id,
        step_index=0,  # same index as existing step
        step_type=AgentStepType.tool_call,
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        status="ok",
    )
    db_session.add(duplicate_step)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_same_step_index_different_runs_allowed(db_session: AsyncSession) -> None:
    """Step index 0 can exist on two different runs without conflict."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    run_a = await _make_agent_run(db_session, scan.id, llm.id)
    run_b = await _make_agent_run(db_session, scan.id, llm.id)

    step_a = await _make_agent_step(db_session, run_a.id, step_index=0)
    step_b = await _make_agent_step(db_session, run_b.id, step_index=0)

    assert step_a.id != step_b.id


# ---------------------------------------------------------------------------
# Cascade delete: AgentRun → steps and actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cascade_delete_run_removes_steps(db_session: AsyncSession) -> None:
    """Deleting an AgentRun deletes its AgentSteps."""
    s = await _build_scaffold(db_session)
    step_id = s["step"].id
    run = s["run"]
    await db_session.commit()

    await db_session.delete(run)
    await db_session.commit()

    result = await db_session.execute(select(AgentStep).where(AgentStep.id == step_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cascade_delete_run_removes_actions(db_session: AsyncSession) -> None:
    """Deleting an AgentRun deletes its RemediationActions."""
    s = await _build_scaffold(db_session)
    action_id = s["action"].id
    run = s["run"]
    await db_session.commit()

    await db_session.delete(run)
    await db_session.commit()

    result = await db_session.execute(
        select(RemediationAction).where(RemediationAction.id == action_id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Cascade delete: Scan → AgentRuns (and transitively steps/actions)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cascade_delete_scan_removes_agent_runs(db_session: AsyncSession) -> None:
    """Deleting a Scan deletes its AgentRuns."""
    s = await _build_scaffold(db_session)
    run_id = s["run"].id
    scan = s["scan"]
    await db_session.commit()

    await db_session.delete(scan)
    await db_session.commit()

    result = await db_session.execute(select(AgentRun).where(AgentRun.id == run_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cascade_delete_scan_removes_steps_transitively(db_session: AsyncSession) -> None:
    """Deleting a Scan transitively removes AgentSteps."""
    s = await _build_scaffold(db_session)
    step_id = s["step"].id
    scan = s["scan"]
    await db_session.commit()

    await db_session.delete(scan)
    await db_session.commit()

    result = await db_session.execute(select(AgentStep).where(AgentStep.id == step_id))
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Cascade delete: Finding → RemediationActions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cascade_delete_finding_removes_actions(db_session: AsyncSession) -> None:
    """Deleting a Finding deletes its RemediationActions."""
    s = await _build_scaffold(db_session)
    action_id = s["action"].id
    finding = s["finding"]
    await db_session.commit()

    await db_session.delete(finding)
    await db_session.commit()

    result = await db_session.execute(
        select(RemediationAction).where(RemediationAction.id == action_id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# RESTRICT: LLMConnection cannot be deleted while AgentRun references it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restrict_delete_llm_connection(db_session: AsyncSession) -> None:
    """Deleting an LLMConnection while an AgentRun references it raises IntegrityError."""
    s = await _build_scaffold(db_session)
    llm = s["llm"]
    await db_session.commit()

    await db_session.delete(llm)

    with pytest.raises(IntegrityError):
        await db_session.commit()


# ---------------------------------------------------------------------------
# Enum round-trips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_run_status_round_trip(db_session: AsyncSession) -> None:
    """All AgentRunStatus values can be stored and read back."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)

    for status in AgentRunStatus:
        run = await _make_agent_run(db_session, scan.id, llm.id, status=status)
        result = await db_session.execute(select(AgentRun).where(AgentRun.id == run.id))
        row = result.scalar_one()
        assert row.status == status


@pytest.mark.asyncio
async def test_agent_step_type_round_trip(db_session: AsyncSession) -> None:
    """All AgentStepType values can be stored and read back."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id)

    for idx, step_type in enumerate(AgentStepType):
        step = await _make_agent_step(db_session, run.id, step_index=idx, step_type=step_type)
        result = await db_session.execute(select(AgentStep).where(AgentStep.id == step.id))
        row = result.scalar_one()
        assert row.step_type == step_type


@pytest.mark.asyncio
async def test_remediation_action_status_round_trip(db_session: AsyncSession) -> None:
    """All RemediationActionStatus values can be stored and read back."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id)
    finding = await _make_finding(db_session, scan.id)

    for status in RemediationActionStatus:
        action = await _make_remediation_action(db_session, run.id, finding.id, status=status)
        result = await db_session.execute(
            select(RemediationAction).where(RemediationAction.id == action.id)
        )
        row = result.scalar_one()
        assert row.status == status


# ---------------------------------------------------------------------------
# Optional/nullable field storage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_step_optional_fields(db_session: AsyncSession) -> None:
    """AgentStep optional fields (prompt_hash, tool_name, etc.) persist correctly."""
    customer = await _make_customer(db_session)
    conn = await _make_connection(db_session, customer.id)
    llm = await _make_llm_connection(db_session, customer.id)
    scan = await _make_scan(db_session, customer.id, conn.id)
    run = await _make_agent_run(db_session, scan.id, llm.id)

    step = AgentStep(
        agent_run_id=run.id,
        step_index=0,
        step_type=AgentStepType.tool_call,
        prompt_hash="abc123" * 10,
        tool_name="create_file",
        tool_args_redacted={"path": "/tmp/test.py", "content": "[redacted]"},
        tool_result_redacted="File created successfully",
        input_tokens=0,
        output_tokens=0,
        latency_ms=50,
        status="ok",
    )
    db_session.add(step)
    await db_session.flush()

    result = await db_session.execute(select(AgentStep).where(AgentStep.id == step.id))
    row = result.scalar_one()

    assert row.tool_name == "create_file"
    assert row.tool_args_redacted == {"path": "/tmp/test.py", "content": "[redacted]"}
    assert row.tool_result_redacted == "File created successfully"


@pytest.mark.asyncio
async def test_remediation_action_pr_fields(db_session: AsyncSession) -> None:
    """RemediationAction PR fields persist when set."""
    s = await _build_scaffold(db_session)
    action = s["action"]

    action.pr_url = "https://github.com/org/repo/pull/42"
    action.branch = "remediate/CICD-008"
    action.status = RemediationActionStatus.opened
    await db_session.flush()

    result = await db_session.execute(
        select(RemediationAction).where(RemediationAction.id == action.id)
    )
    row = result.scalar_one()

    assert row.pr_url == "https://github.com/org/repo/pull/42"
    assert row.branch == "remediate/CICD-008"
    assert row.status == RemediationActionStatus.opened
