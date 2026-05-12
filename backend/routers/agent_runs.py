from __future__ import annotations

"""REST + SSE router for the remediation agent run lifecycle.

Endpoints
---------
POST   /api/scans/{scan_id}/agent-runs      — Trigger a new agent run
GET    /api/agent-runs                       — List runs (filterable)
GET    /api/agent-runs/estimate              — Cost estimate for a scan
GET    /api/agent-runs/{id}                  — Fetch single run (with steps/actions)
POST   /api/agent-runs/{id}/cancel          — Request cancellation
GET    /api/agent-runs/{id}/stream          — SSE stream of AgentStep events
POST   /api/agent-runs/{id}/events          — Receive CI-mode step events (HMAC-signed)

Issue: #27, #47
"""

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import AsyncSessionLocal, get_db
from backend.models.agent_runs import AgentRun, AgentStep
from backend.models.enums import AgentRunStatus
from backend.schemas.agent_runs import (
    AgentRunListItem,
    AgentRunRead,
    AgentRunTriggerPayload,
    AgentStepEventPayload,
    AgentStepRead,
)
from backend.services import agent_service
from backend.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent-runs"])

# ---------------------------------------------------------------------------
# Terminal-state set (reused in both cancel and stream endpoints)
# ---------------------------------------------------------------------------

_TERMINAL: frozenset[object] = frozenset(
    {
        AgentRunStatus.completed,
        AgentRunStatus.failed,
        AgentRunStatus.cancelled,
        # String forms for SQLite compatibility in tests.
        "completed",
        "failed",
        "cancelled",
    }
)


# ---------------------------------------------------------------------------
# Helper: SSE wire format
# ---------------------------------------------------------------------------


def _format_sse_event(event_id: int, event_type: str, data: str) -> bytes:
    """Encode a single SSE event per the W3C spec.

    Wire format::

        id: <event_id>
        event: <event_type>
        data: <data>
        \\n

    Args:
        event_id: Monotonic integer used as the SSE ``id`` field.
        event_type: SSE ``event`` field value (e.g. ``"llm_call"``,
            ``"status_change"``).
        data: JSON-serialised string placed in the SSE ``data`` field.

    Returns:
        UTF-8 encoded bytes ready to write to the response stream.
    """
    return f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n".encode()


def _enum_value(v: object) -> str:
    """Return the string value of an enum member or the string itself.

    SQLite returns enum columns as plain strings while PostgreSQL returns
    proper enum instances.  This helper normalises both cases.

    Args:
        v: An enum instance or a plain string.

    Returns:
        The underlying string value.
    """
    return v.value if hasattr(v, "value") else str(v)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# HMAC verification helper (issue #47)
# ---------------------------------------------------------------------------


def verify_signature(body: bytes, secret: bytes, header: str | None) -> bool:
    """Constant-time HMAC-SHA256 verification of *body* using *secret*.

    Expected header format: ``sha256=<hex_digest>``. Returns ``False`` for any
    malformed header, missing prefix, or mismatched digest.

    Args:
        body: Raw request body bytes to authenticate.
        secret: 32-byte HMAC key stored in :attr:`AgentRun.callback_secret`.
        header: Value of the ``X-BPS-Signature`` request header; ``None`` if
            the header was absent.

    Returns:
        ``True`` iff the computed digest matches the received digest using a
        constant-time comparison.
    """
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    received = header.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, received)


# ---------------------------------------------------------------------------
# Step lookup helper (issue #47)
# ---------------------------------------------------------------------------


async def _get_step(
    db: AsyncSession,
    run_id: UUID,
    step_index: int,
) -> AgentStep | None:
    """Return the existing :class:`AgentStep` for *(run_id, step_index)* or ``None``.

    Args:
        db: Active async database session.
        run_id: UUID of the owning :class:`AgentRun`.
        step_index: Zero-based step counter to look up.

    Returns:
        The matching :class:`AgentStep` row or ``None`` if not present.
    """
    stmt = select(AgentStep).where(
        AgentStep.agent_run_id == run_id,
        AgentStep.step_index == step_index,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# POST /api/scans/{scan_id}/agent-runs — Trigger
# ---------------------------------------------------------------------------


@router.post(
    "/scans/{scan_id}/agent-runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger a remediation agent run for a completed scan",
)
async def trigger_agent_run(
    scan_id: UUID,
    payload: AgentRunTriggerPayload,
    db: AsyncSession = Depends(get_db),
) -> AgentRun:
    """Trigger an AgentRun for a completed scan.

    Creates a new :class:`~backend.models.agent_runs.AgentRun` in ``pending``
    state and schedules the backend runner as a fire-and-forget background
    task.

    Clients should monitor progress via the SSE stream endpoint
    ``GET /api/agent-runs/{id}/stream`` or by polling
    ``GET /api/agent-runs/{id}``.

    # TODO: gate behind require_role("customer_member")

    Args:
        scan_id: UUID of the completed scan to remediate.
        payload: Trigger payload containing ``llm_connection_id``,
            ``runtime_mode``, and optional ``check_ids``.
        db: Injected async database session.

    Returns:
        The newly created :class:`~backend.models.agent_runs.AgentRun` in
        ``pending`` status.

    Raises:
        HTTPException: 404 when the scan or LLM connection is not found.
        HTTPException: 409 when the scan is not completed or a non-terminal
            run already exists.
    """
    run = await agent_service.create_agent_run(
        db,
        scan_id=scan_id,
        llm_connection_id=payload.llm_connection_id,
        runtime_mode=payload.runtime_mode,
        check_ids=payload.check_ids,
    )
    await agent_service.trigger_backend_run(run, AsyncSessionLocal)
    # Re-fetch with relationships to satisfy AgentRunRead (steps + actions).
    stmt = (
        select(AgentRun)
        .where(AgentRun.id == run.id)
        .options(selectinload(AgentRun.steps), selectinload(AgentRun.actions))
    )
    run = (await db.execute(stmt)).scalar_one()
    return run


# ---------------------------------------------------------------------------
# GET /api/agent-runs/estimate — Cost estimate (must be before /{id} route)
# ---------------------------------------------------------------------------


@router.get(
    "/agent-runs/estimate",
    summary="Estimate cost for a remediation run on a scan",
)
async def estimate(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a rough cost estimate for running the remediation agent.

    Uses the count of failing findings and the customer's default LLM
    connection to compute ``min_usd``, ``max_usd``, and
    ``expected_tokens``.

    # TODO: gate behind require_role("customer_member")

    Args:
        scan_id: UUID of the scan to estimate.
        db: Injected async database session.

    Returns:
        ``{"min_usd": float, "max_usd": float, "expected_tokens": int}``

    Raises:
        HTTPException: 404 when the scan is not found.
    """
    return await agent_service.estimate_run_cost(db, scan_id)


# ---------------------------------------------------------------------------
# GET /api/agent-runs — List
# ---------------------------------------------------------------------------


@router.get(
    "/agent-runs",
    response_model=list[AgentRunListItem],
    summary="List agent runs with optional filters",
)
async def list_agent_runs(
    scan_id: UUID | None = None,
    customer_id: UUID | None = None,
    status: AgentRunStatus | None = None,
    since: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[AgentRun]:
    """Return a paginated list of :class:`~backend.models.agent_runs.AgentRun` rows.

    Results are sorted by ``started_at DESC NULLS LAST, created_at DESC``.
    The ``pr_count`` field in list items is always ``0`` in this v1 response;
    use the detail endpoint to access the full ``actions`` list.

    # TODO: gate behind require_role(...)

    Args:
        scan_id: Filter to a specific scan.
        customer_id: Filter to all scans belonging to a customer (joins
            through ``scans``).
        status: Filter to a specific run status.
        since: Return only runs whose ``started_at`` is at or after this
            ISO-8601 timestamp.
        limit: Maximum number of results (capped at 200; default 50).
        offset: Number of rows to skip for pagination (default 0).
        db: Injected async database session.

    Returns:
        List of :class:`~backend.schemas.agent_runs.AgentRunListItem` dicts.
    """
    # TODO: gate behind require_role(...)
    limit = min(limit, 200)

    stmt = select(AgentRun).order_by(
        AgentRun.started_at.desc().nullslast(),
        AgentRun.created_at.desc(),
    )

    if scan_id is not None:
        stmt = stmt.where(AgentRun.scan_id == scan_id)

    if customer_id is not None:
        from backend.models.scan import Scan  # noqa: PLC0415

        stmt = stmt.join(Scan, AgentRun.scan_id == Scan.id).where(Scan.customer_id == customer_id)

    if status is not None:
        stmt = stmt.where(AgentRun.status == status)

    if since is not None:
        stmt = stmt.where(AgentRun.started_at >= since)

    stmt = stmt.limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# GET /api/agent-runs/{id} — Detail
# ---------------------------------------------------------------------------


@router.get(
    "/agent-runs/{id}",
    response_model=AgentRunRead,
    summary="Fetch a single agent run with steps and actions",
)
async def get_agent_run(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentRun:
    """Return the full :class:`~backend.models.agent_runs.AgentRun` record.

    Eagerly loads ``steps`` (ordered by ``step_index`` ascending) and
    ``actions``.

    # TODO: gate behind require_role(...)

    Args:
        id: UUID of the agent run.
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.agent_runs.AgentRunRead`.

    Raises:
        HTTPException: 404 when no run with *id* exists.
    """
    # TODO: gate behind require_role(...)
    stmt = (
        select(AgentRun)
        .where(AgentRun.id == id)
        .options(selectinload(AgentRun.steps), selectinload(AgentRun.actions))
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AgentRun {id} not found.",
        )
    # selectinload does not guarantee order; sort here to be safe.
    run.steps.sort(key=lambda s: s.step_index)
    return run


# ---------------------------------------------------------------------------
# POST /api/agent-runs/{id}/cancel — Cancel
# ---------------------------------------------------------------------------


@router.post(
    "/agent-runs/{id}/cancel",
    response_model=AgentRunRead,
    summary="Request cancellation of an agent run",
)
async def cancel(
    id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentRun:
    """Request cancellation of an in-flight agent run.

    Idempotent: returns the run unchanged if it is already in a terminal
    state (completed / failed / cancelled).

    # TODO: gate behind require_role(...)

    Args:
        id: UUID of the agent run to cancel.
        db: Injected async database session.

    Returns:
        The (possibly updated) :class:`~backend.schemas.agent_runs.AgentRunRead`.

    Raises:
        HTTPException: 404 when no run with *id* exists.
    """
    # TODO: gate behind require_role(...)
    cancelled_run = await agent_service.cancel_agent_run(db, id)
    # Re-fetch with relationships to satisfy AgentRunRead (steps + actions).
    stmt = (
        select(AgentRun)
        .where(AgentRun.id == cancelled_run.id)
        .options(selectinload(AgentRun.steps), selectinload(AgentRun.actions))
    )
    result = (await db.execute(stmt)).scalar_one()
    result.steps.sort(key=lambda s: s.step_index)
    return result


# ---------------------------------------------------------------------------
# POST /api/agent-runs/{id}/events — CI-mode runner webhook (issue #47)
# ---------------------------------------------------------------------------


@router.post(
    "/agent-runs/{id}/events",
    response_model=AgentStepRead,
    status_code=status.HTTP_200_OK,
    summary="Receive a HMAC-signed CI-mode agent step event",
)
async def receive_event(
    id: UUID,
    request: Request,
    x_bps_signature: str | None = Header(default=None, alias="X-BPS-Signature"),
    db: AsyncSession = Depends(get_db),
) -> AgentStep:
    """Receive a CI-mode agent step event.

    Body: :class:`~backend.schemas.agent_runs.AgentStepEventPayload` (JSON).
    Signature header: ``X-BPS-Signature: sha256=<hex_hmac_of_body>``.

    Idempotency: if a row with ``(agent_run_id, step_index)`` already exists,
    returns the existing row with 200.  Use this for at-least-once webhook
    retries from the CI runner.

    On commit races (concurrent duplicate POSTs that slip past the pre-check),
    the ``uq_agent_steps_run_index`` DB constraint raises
    :class:`~sqlalchemy.exc.IntegrityError`; the handler rolls back, re-reads
    the existing row, and returns it with 200.

    Args:
        id: UUID of the target :class:`~backend.models.agent_runs.AgentRun`.
        request: Raw FastAPI request; the full body is read for HMAC verification.
        x_bps_signature: Value of the ``X-BPS-Signature`` header; ``None`` if absent.
        db: Injected async database session.

    Returns:
        The newly created or already-existing
        :class:`~backend.models.agent_runs.AgentStep` row.

    Raises:
        HTTPException: 404 when no run with *id* exists.
        HTTPException: 401 when the HMAC signature is absent or invalid.
        HTTPException: 500 when a commit race cannot be resolved (should not
            occur in normal operation).
    """
    body_bytes = await request.body()
    run = await db.get(AgentRun, id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AgentRun {id} not found",
        )
    if not verify_signature(body_bytes, run.callback_secret, x_bps_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    try:
        payload = AgentStepEventPayload.model_validate_json(body_bytes)
    except PydanticValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(include_url=False),
        ) from exc

    # Idempotency: return existing row without re-inserting.
    existing = await _get_step(db, id, payload.step_index)
    if existing is not None:
        return existing

    step = AgentStep(
        agent_run_id=id,
        step_index=payload.step_index,
        step_type=payload.step_type,
        prompt_hash=payload.prompt_hash,
        tool_name=payload.tool_name,
        tool_args_redacted=payload.tool_args_redacted,
        tool_result_redacted=payload.tool_result_redacted,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        latency_ms=payload.latency_ms,
        status=payload.status,
    )
    db.add(step)
    try:
        await db.commit()
    except IntegrityError:
        # Race: a concurrent retry inserted the same step_index between our
        # pre-check and this insert.  Roll back and re-read.
        await db.rollback()
        existing = await _get_step(db, id, payload.step_index)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Step insert race; please retry",
            ) from None
        return existing
    await db.refresh(step)

    # Publish to the SSE event bus for live consumers.
    event_bus = get_event_bus()
    await event_bus.publish(
        id,
        {
            "step_index": payload.step_index,
            "step_type": _enum_value(payload.step_type),
            "tool_name": payload.tool_name,
            "tool_args_redacted": payload.tool_args_redacted,
            "tool_result_redacted": payload.tool_result_redacted,
            "input_tokens": payload.input_tokens,
            "output_tokens": payload.output_tokens,
            "latency_ms": payload.latency_ms,
            "status": payload.status,
            "created_at": step.created_at.isoformat() if step.created_at is not None else None,
        },
    )

    return step


# ---------------------------------------------------------------------------
# GET /api/agent-runs/{id}/stream — SSE
# ---------------------------------------------------------------------------


@router.get(
    "/agent-runs/{id}/stream",
    summary="Stream live AgentStep events via Server-Sent Events",
)
async def stream_agent_run(
    id: UUID,
    last_event_id: int | None = Header(None, alias="Last-Event-ID"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream :class:`~backend.models.agent_runs.AgentStep` events as SSE.

    Protocol
    --------
    1. Verify the run exists (404 if not).
    2. Subscribe to the in-process :class:`~backend.services.event_bus.EventBus`
       queue **first** so no live events are lost during replay.
    3. Replay persisted :class:`~backend.models.agent_runs.AgentStep` rows
       with ``step_index > Last-Event-ID`` (or all rows when the header is
       absent).
    4. Forward live events from the queue, deduplicating any whose
       ``step_index`` falls within the already-replayed range.
    5. Emit a heartbeat ``:\\n\\n`` every 15 seconds to keep the connection
       alive through proxies and load balancers.
    6. Close automatically when the run reaches a terminal state and a
       ``status_change`` event has been emitted.

    Resume
    ------
    Clients that reconnect after a disconnect should pass the ``Last-Event-ID``
    header set to the highest ``id:`` value they received.  The server will
    skip steps up to and including that index.

    Args:
        id: UUID of the agent run to stream.
        last_event_id: Optional highest step index already received by the
            client (from the SSE ``Last-Event-ID`` header).
        db: Injected async database session.

    Returns:
        :class:`fastapi.responses.StreamingResponse` with
        ``Content-Type: text/event-stream``.

    Raises:
        HTTPException: 404 when no run with *id* exists.
    """
    run = await db.get(AgentRun, id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AgentRun {id} not found.",
        )

    event_bus = get_event_bus()

    async def gen() -> AsyncIterator[bytes]:
        async with event_bus.subscribe(id) as queue:
            # --- 1. Replay persisted steps -----------------------------------
            # Use the injected `db` session (captured in closure) for all DB
            # reads so that the test DB override (get_db) applies here too.
            since_index: int = last_event_id if last_event_id is not None else -1
            replay_stmt = (
                select(AgentStep)
                .where(AgentStep.agent_run_id == id)
                .where(AgentStep.step_index > since_index)
                .order_by(AgentStep.step_index.asc())
            )
            replay_rows = (await db.execute(replay_stmt)).scalars().all()

            max_replayed_index = since_index
            for step in replay_rows:
                yield _format_sse_event(
                    step.step_index,
                    _enum_value(step.step_type),
                    AgentStepRead.model_validate(step).model_dump_json(),
                )
                max_replayed_index = max(max_replayed_index, step.step_index)

            # --- 2. Check whether the run is already terminal ----------------
            # Expire the cached run to force a fresh read from the DB.
            await db.refresh(run)
            if run.status in _TERMINAL:
                finished_at_str = (
                    run.finished_at.isoformat() if run.finished_at is not None else None
                )
                yield _format_sse_event(
                    max_replayed_index + 1,
                    "status_change",
                    json.dumps(
                        {
                            "status": _enum_value(run.status),
                            "finished_at": finished_at_str,
                        }
                    ),
                )
                return

            # --- 3. Forward live events with heartbeats ----------------------
            while True:
                try:
                    event: dict = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield b":\n\n"  # SSE heartbeat comment
                    # Check terminal state on each heartbeat timeout.
                    await db.refresh(run)
                    if run.status in _TERMINAL:
                        return
                    continue

                step_index: int = event.get("step_index", max_replayed_index + 1)
                if step_index <= max_replayed_index:
                    continue  # dedup overlap from replay/live boundary

                event_type: str = str(event.get("step_type", event.get("event", "message")))
                yield _format_sse_event(step_index, event_type, json.dumps(event))
                max_replayed_index = max(max_replayed_index, step_index)

                # Terminal events close the stream.
                if event.get("step_type") == "final" or event.get("event") == "status_change":
                    return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
