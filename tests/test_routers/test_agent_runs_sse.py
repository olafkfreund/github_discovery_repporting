from __future__ import annotations

"""SSE streaming endpoint tests for /api/agent-runs/{id}/stream (issue #27).

Uses httpx.AsyncClient with ASGITransport and collects the full response body
to parse SSE event blocks.  The streaming generator closes after emitting a
final/status_change event or when the run is already in a terminal state.
"""

import json
import secrets
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.main import app
from backend.models.agent_runs import AgentRun, AgentStep
from backend.models.enums import AgentRunStatus, AgentStepType
from backend.services.event_bus import EventBus

# ---------------------------------------------------------------------------
# SSE parsing helper
# ---------------------------------------------------------------------------


def _parse_sse_events(raw: bytes) -> list[dict[str, str]]:
    """Parse raw SSE bytes into a list of event dicts with keys id/event/data.

    Each SSE event block is separated by a blank line (\\n\\n).  Heartbeat
    comments (``: \\n\\n``) are skipped.

    Args:
        raw: Raw bytes from the response body.

    Returns:
        List of dicts, each with keys ``id``, ``event``, and ``data``.
    """
    events: list[dict[str, str]] = []
    blocks = raw.decode("utf-8").split("\n\n")
    for block in blocks:
        block = block.strip()
        if not block or block.startswith(":"):
            continue  # heartbeat or empty
        ev: dict[str, str] = {}
        for line in block.splitlines():
            if ": " in line:
                key, _, val = line.partition(": ")
                ev[key.strip()] = val.strip()
        if ev:
            events.append(ev)
    return events


# ---------------------------------------------------------------------------
# Shared fixture helpers (inline — no conftest pollution)
# ---------------------------------------------------------------------------


async def _make_agent_run(
    db: AsyncSession,
    *,
    status: AgentRunStatus = AgentRunStatus.running,
) -> AgentRun:
    """Insert a minimal AgentRun; caller must commit."""
    from backend.models.customer import Customer, PlatformConnection
    from backend.models.enums import AuthType, LLMProviderEnum, Platform, ScanStatus
    from backend.models.llm import LLMConnection
    from backend.models.scan import Scan
    from backend.services.secrets_service import secrets_service

    uid = uuid.uuid4().hex[:6]
    customer = Customer(name=f"SSECorp {uid}", slug=f"ssecorp-{uid}")
    db.add(customer)
    await db.flush()

    conn = PlatformConnection(
        customer_id=customer.id,
        platform=Platform.github,
        display_name="GH",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(json.dumps({"token": "tok"})),
        org_or_group="org",
        is_active=True,
    )
    db.add(conn)
    await db.flush()

    llm = LLMConnection(
        customer_id=customer.id,
        name=f"llm-{uid}",
        provider=LLMProviderEnum.anthropic,
        model="claude-sonnet-4-6",
        is_default=True,
    )
    db.add(llm)
    await db.flush()

    scan = Scan(customer_id=customer.id, connection_id=conn.id, status=ScanStatus.completed)
    db.add(scan)
    await db.flush()

    run = AgentRun(
        scan_id=scan.id,
        llm_connection_id=llm.id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        status=status,
        runtime_mode="backend",
        callback_secret=secrets.token_bytes(32),
    )
    db.add(run)
    await db.flush()
    return run


async def _make_steps(
    db: AsyncSession,
    agent_run_id: uuid.UUID,
    count: int,
    start: int = 0,
) -> list[AgentStep]:
    """Insert *count* AgentStep rows with sequential step_index values."""
    steps: list[AgentStep] = []
    for i in range(start, start + count):
        step = AgentStep(
            agent_run_id=agent_run_id,
            step_index=i,
            step_type=AgentStepType.llm_call,
            input_tokens=5,
            output_tokens=5,
            latency_ms=10,
            status="ok",
        )
        db.add(step)
        steps.append(step)
    await db.flush()
    return steps


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_404_missing_run(db_session: AsyncSession) -> None:
    """GET /api/agent-runs/{id}/stream returns 404 for an unknown run id."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as ac:
        resp = await ac.get(f"/api/agent-runs/{uuid.uuid4()}/stream")
    assert resp.status_code == 404

    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_sse_terminal_run_closes_immediately(db_session: AsyncSession) -> None:
    """A completed run with no steps emits status_change and closes the stream."""
    run = await _make_agent_run(db_session, status=AgentRunStatus.completed)
    await db_session.commit()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as ac:
        resp = await ac.get(f"/api/agent-runs/{run.id}/stream")

    assert resp.status_code == 200
    events = _parse_sse_events(resp.content)
    assert any(ev.get("event") == "status_change" for ev in events), (
        f"Expected status_change event; got: {events}"
    )

    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_sse_replay_persisted_steps(db_session: AsyncSession) -> None:
    """SSE replays all 5 persisted AgentStep rows without Last-Event-ID."""
    run = await _make_agent_run(db_session, status=AgentRunStatus.completed)
    await _make_steps(db_session, run.id, count=5)
    await db_session.commit()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as ac:
        resp = await ac.get(f"/api/agent-runs/{run.id}/stream")

    assert resp.status_code == 200
    events = _parse_sse_events(resp.content)
    # 5 step events + 1 status_change = 6 total
    step_events = [ev for ev in events if ev.get("event") != "status_change"]
    assert len(step_events) == 5, f"Expected 5 step events; got {len(step_events)}: {events}"
    # Verify each step event has the expected SSE fields.
    for ev in step_events:
        assert "id" in ev
        assert "event" in ev
        assert "data" in ev
    # Verify ascending step_index order.
    ids = [int(ev["id"]) for ev in step_events]
    assert ids == sorted(ids)

    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_sse_resume_with_last_event_id(db_session: AsyncSession) -> None:
    """SSE with Last-Event-ID: 2 replays only step_index 3, 4."""
    run = await _make_agent_run(db_session, status=AgentRunStatus.completed)
    await _make_steps(db_session, run.id, count=5)  # step_index 0-4
    await db_session.commit()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as ac:
        resp = await ac.get(
            f"/api/agent-runs/{run.id}/stream",
            headers={"Last-Event-ID": "2"},
        )

    assert resp.status_code == 200
    events = _parse_sse_events(resp.content)
    step_events = [ev for ev in events if ev.get("event") != "status_change"]
    # Only step_index 3 and 4 should be replayed (> 2).
    assert len(step_events) == 2, f"Expected 2 step events; got {len(step_events)}: {events}"
    ids = [int(ev["id"]) for ev in step_events]
    assert min(ids) == 3  # noqa: PLR2004

    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_sse_live_events_via_event_bus(db_session: AsyncSession) -> None:
    """SSE receives live events published via the event_bus after subscribe."""
    run = await _make_agent_run(db_session, status=AgentRunStatus.running)
    await db_session.commit()

    # Replace the singleton event bus with a fresh one for test isolation.
    test_bus = EventBus()
    run_id = run.id

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    import backend.routers.agent_runs as agent_runs_module
    import backend.services.event_bus as event_bus_module

    original_get_event_bus = event_bus_module.get_event_bus

    def _patched_get_event_bus() -> EventBus:
        return test_bus

    event_bus_module.get_event_bus = _patched_get_event_bus  # type: ignore[assignment]
    agent_runs_module.get_event_bus = _patched_get_event_bus  # type: ignore[assignment]

    # Pre-publish 2 live events (before anyone subscribes — simulates the runner
    # publishing before the SSE subscriber connects, which the queue buffers).
    await test_bus.publish(run_id, {"step_index": 0, "step_type": "llm_call", "input_tokens": 5})
    await test_bus.publish(
        run_id, {"step_index": 1, "step_type": "tool_call", "tool_name": "read_file"}
    )
    # Publish a final event so the stream closes.
    await test_bus.publish(run_id, {"step_index": 2, "step_type": "final", "summary": "done"})

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(f"/api/agent-runs/{run.id}/stream")

        assert resp.status_code == 200
        events = _parse_sse_events(resp.content)
        step_events = [ev for ev in events if ev.get("event") != "status_change"]
        # All 3 live events should have been received.
        assert len(step_events) == 3, f"Expected 3 live events; got {len(step_events)}: {events}"
        # The last event should be the 'final' type.
        assert step_events[-1]["event"] == "final"
    finally:
        event_bus_module.get_event_bus = original_get_event_bus  # type: ignore[assignment]
        agent_runs_module.get_event_bus = original_get_event_bus  # type: ignore[assignment]
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_sse_dedup_overlap(db_session: AsyncSession) -> None:
    """Events already replayed from DB are not duplicated when also in the queue."""
    run = await _make_agent_run(db_session, status=AgentRunStatus.running)
    # Persist steps 0-2.
    await _make_steps(db_session, run.id, count=3)
    await db_session.commit()

    test_bus = EventBus()
    run_id = run.id

    # Pre-publish events that overlap with persisted steps (step_index 1-2)
    # plus one new step (3) and a final close event (4).
    await test_bus.publish(run_id, {"step_index": 1, "step_type": "llm_call"})
    await test_bus.publish(run_id, {"step_index": 2, "step_type": "tool_call"})
    await test_bus.publish(run_id, {"step_index": 3, "step_type": "observation"})
    await test_bus.publish(run_id, {"step_index": 4, "step_type": "final"})

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    import backend.routers.agent_runs as agent_runs_module
    import backend.services.event_bus as event_bus_module

    original_get_event_bus = event_bus_module.get_event_bus

    def _patched_get_event_bus() -> EventBus:
        return test_bus

    event_bus_module.get_event_bus = _patched_get_event_bus  # type: ignore[assignment]
    agent_runs_module.get_event_bus = _patched_get_event_bus  # type: ignore[assignment]

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get(f"/api/agent-runs/{run.id}/stream")

        assert resp.status_code == 200
        events = _parse_sse_events(resp.content)
        step_events = [ev for ev in events if ev.get("event") != "status_change"]
        ids = [int(ev["id"]) for ev in step_events]
        # Duplicate ids must not appear.
        assert len(ids) == len(set(ids)), f"Duplicate step indices in SSE stream: {ids}"
        # Steps 0, 1, 2 from DB + 3, 4 from live queue (1 and 2 deduped) = 5 unique.
        assert sorted(ids) == [0, 1, 2, 3, 4], f"Unexpected step ids: {ids}"
    finally:
        event_bus_module.get_event_bus = original_get_event_bus  # type: ignore[assignment]
        agent_runs_module.get_event_bus = original_get_event_bus  # type: ignore[assignment]
        app.dependency_overrides.pop(get_db, None)
