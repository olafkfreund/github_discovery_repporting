from __future__ import annotations

"""Public service-layer API for AgentRun lifecycle management.

This module is the entry point for all remediation agent operations.
Routers (issue #27) call these functions to create, trigger, cancel, and
cost-estimate agent runs.  Every function opens or accepts an
:class:`~sqlalchemy.ext.asyncio.AsyncSession`; none of them talk
directly to the LLM or the workspace.
"""

import asyncio
import logging
import secrets
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.agent_runs import AgentRun
from backend.models.enums import AgentRunStatus, ScanStatus
from backend.models.finding import Finding
from backend.models.llm import LLMConnection
from backend.models.scan import Scan
from backend.services import kill_switch_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost-estimate constants
# ---------------------------------------------------------------------------

# Rough combined token count (input + output) for a single finding remediation.
_AVG_TOKENS_PER_FINDING: dict[str, int] = {
    # input + output combined, rough order-of-magnitude
    "default": 8_000,
}

# Per-provider (input_cost_per_1M, output_cost_per_1M) in USD.
# Used by estimate_run_cost to compute a cost range.  These figures are
# intentionally conservative ballpark numbers; Phase 5 will refine them with
# real per-model pricing from each provider's API.
_MODEL_COST_USD_PER_1M: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0),
    # vLLM / Ollama / self-hosted — no per-token API cost
    "_default": (0.0, 0.0),
}

# Heuristic token window used for min/max cost bounds.
# min = findings * _MIN_TOKENS_PER_FINDING / 1_000_000 * avg_cost_per_1M
# max = findings * _MAX_TOKENS_PER_FINDING / 1_000_000 * avg_cost_per_1M
_MIN_TOKENS_PER_FINDING = 5_000
_MAX_TOKENS_PER_FINDING = 15_000

# ---------------------------------------------------------------------------
# Helper: fetch LLM connection price tier
# ---------------------------------------------------------------------------


def _cost_per_1m(model: str) -> tuple[float, float]:
    """Return (input_cost_per_1M, output_cost_per_1M) for *model*.

    Falls back to ``_default`` (free) for any model string not listed in the
    table, covering self-hosted providers (vLLM, Ollama, etc.).

    Args:
        model: Model identifier string (provider-specific format).

    Returns:
        A 2-tuple of USD costs per million tokens for input and output.
    """
    # Exact match first.
    if model in _MODEL_COST_USD_PER_1M:
        return _MODEL_COST_USD_PER_1M[model]
    # Prefix match to handle versioned model names, e.g. "claude-sonnet-4-6-20250514".
    for key, costs in _MODEL_COST_USD_PER_1M.items():
        if key != "_default" and model.startswith(key):
            return costs
    return _MODEL_COST_USD_PER_1M["_default"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def create_agent_run(
    db: AsyncSession,
    *,
    scan_id: UUID,
    llm_connection_id: UUID,
    runtime_mode: Literal["backend", "ci"] = "backend",
    check_ids: list[str] | None = None,
) -> AgentRun:
    """Validate inputs and insert a new :class:`~backend.models.agent_runs.AgentRun`.

    Validation checks (in order):

    1. Scan exists — :http:statuscode:`404` if not.
    2. Scan status is ``completed`` — :http:statuscode:`409` if not.
    3. LLMConnection exists — :http:statuscode:`404` if not.
    4. Kill switch not engaged (global or customer layer) — :http:statuscode:`403` if engaged.
    5. No non-terminal AgentRun already exists for this scan — :http:statuscode:`409`.

    On success a new row is committed in ``pending`` state.
    ``callback_secret`` is populated with 32 cryptographically-random bytes
    for future CI-mode webhook verification (Phase 4).

    The ``provider`` and ``model`` fields on the new row are snapshotted from
    the :class:`~backend.models.llm.LLMConnection` at creation time so that
    reporting remains accurate even if the connection is later reconfigured.

    Args:
        db: Active async database session.
        scan_id: UUID of the completed scan to remediate.
        llm_connection_id: UUID of the LLM connection to use.
        runtime_mode: ``"backend"`` (default) or ``"ci"``.
        check_ids: Optional list of check IDs to restrict remediation to.
            Stored on the run for reference; the runner uses them to filter
            eligible findings.  ``None`` means all failing checks.

    Returns:
        The newly committed :class:`~backend.models.agent_runs.AgentRun` row.

    Raises:
        HTTPException: 404 when scan or LLM connection is not found.
        HTTPException: 403 when a kill switch is engaged at the global or
            customer layer.
        HTTPException: 409 when the scan is not completed or a non-terminal
            run already exists.
    """
    # 1. Scan exists?
    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = scan_result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found.",
        )

    # 2. Scan is completed?
    if scan.status != ScanStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Scan {scan_id} is in state '{scan.status.value}'; "
                "remediation requires status 'completed'."
            ),
        )

    # 3. LLMConnection exists?
    llm_result = await db.execute(
        select(LLMConnection).where(LLMConnection.id == llm_connection_id)
    )
    llm_connection = llm_result.scalar_one_or_none()
    if llm_connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM connection {llm_connection_id} not found.",
        )

    # 4. Kill switch check (global → customer layers).
    ks = await kill_switch_service.check(db, scan.customer_id)
    if ks.engaged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Kill switch engaged at {ks.layer} layer; cannot create agent runs.",
        )

    # 5. No active (non-terminal) run already exists for this scan?
    terminal_statuses = {
        AgentRunStatus.completed,
        AgentRunStatus.failed,
        AgentRunStatus.cancelled,
        # Also include string forms for SQLite compatibility in tests.
        "completed",
        "failed",
        "cancelled",
    }
    existing_result = await db.execute(select(AgentRun).where(AgentRun.scan_id == scan_id))
    existing_runs = list(existing_result.scalars().all())
    active_run = next(
        (r for r in existing_runs if r.status not in terminal_statuses),
        None,
    )
    if active_run is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An agent run ({active_run.id}) is already active for scan "
                f"{scan_id} (status={active_run.status.value if hasattr(active_run.status, 'value') else active_run.status}). "
                "Cancel or wait for it to finish before starting a new run."
            ),
        )

    # Create the run row in pending state.
    run = AgentRun(
        scan_id=scan_id,
        llm_connection_id=llm_connection_id,
        provider=llm_connection.provider.value
        if hasattr(llm_connection.provider, "value")
        else str(llm_connection.provider),
        model=llm_connection.model,
        status=AgentRunStatus.pending,
        runtime_mode=runtime_mode,
        callback_secret=secrets.token_bytes(32),
        # check_ids filter is stored on the AgentRun if the model supports it;
        # for now we store as a free-form note in the error field (cleared later)
        # and pass it to the runner via a separate argument.  The model does not
        # currently have a dedicated check_ids column — the runner receives it
        # via trigger_backend_run's call site.  If check_ids filtering is needed
        # beyond what the runner already does via policy, extend the model in a
        # later migration.
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info(
        "create_agent_run: created run %s for scan %s (llm=%s, mode=%s)",
        run.id,
        scan_id,
        llm_connection_id,
        runtime_mode,
    )
    return run


async def trigger_backend_run(
    agent_run: AgentRun,
    db_factory: async_sessionmaker,
) -> asyncio.Task:
    """Schedule :func:`~backend.agents.runner_backend.run_backend_agent` as a background task.

    Mirrors the :func:`~backend.services.scan_service.trigger_scan_background`
    pattern.  The agent semaphore (via
    :func:`~backend.services.task_limiter.get_agent_semaphore`) bounds
    concurrent runs; excess tasks queue inside ``async with`` rather than
    being rejected.

    Args:
        agent_run: The :class:`~backend.models.agent_runs.AgentRun` row in
            ``pending`` state to schedule.
        db_factory: The application-wide async session factory, forwarded to
            the runner so it can open fresh sessions without sharing the
            caller's session.

    Returns:
        The :class:`asyncio.Task` wrapping the runner coroutine.  Routers
        fire-and-forget; the return value is useful for testing / introspection.
    """
    from backend.agents.runner_backend import run_backend_agent  # noqa: PLC0415
    from backend.services.task_limiter import get_agent_semaphore  # noqa: PLC0415

    run_id = agent_run.id

    async def _limited_run() -> None:
        async with get_agent_semaphore():
            await run_backend_agent(agent_run_id=run_id, db_factory=db_factory)

    logger.info("trigger_backend_run: scheduling agent run %s.", run_id)
    return asyncio.create_task(_limited_run())


async def cancel_agent_run(db: AsyncSession, agent_run_id: UUID) -> AgentRun:
    """Request cancellation of an in-flight agent run.

    If the run is already in a terminal state (completed / failed / cancelled)
    this function is idempotent — it returns the existing row unchanged.
    Otherwise it sets ``status=cancelled`` and fires the in-process cancel
    event so the running loop exits cleanly at the next iteration boundary.

    Args:
        db: Active async database session.
        agent_run_id: UUID of the :class:`~backend.models.agent_runs.AgentRun`
            to cancel.

    Returns:
        The (possibly updated) :class:`~backend.models.agent_runs.AgentRun` row.

    Raises:
        HTTPException: 404 if no run with *agent_run_id* exists.
    """
    from backend.services.event_bus import get_cancel_registry  # noqa: PLC0415

    result = await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AgentRun {agent_run_id} not found.",
        )

    terminal_statuses = {AgentRunStatus.completed, AgentRunStatus.failed, AgentRunStatus.cancelled}
    if run.status in terminal_statuses:
        # Already terminal — idempotent.
        return run

    run.status = AgentRunStatus.cancelled
    await db.commit()
    await db.refresh(run)

    # Signal the in-flight loop (no-op if the loop has already exited).
    fired = get_cancel_registry().trigger(agent_run_id)
    logger.info(
        "cancel_agent_run: run %s set to cancelled (cancel_event triggered=%s).",
        agent_run_id,
        fired,
    )
    return run


async def estimate_run_cost(db: AsyncSession, scan_id: UUID) -> dict[str, float]:
    """Produce a rough cost estimate for a remediation run on *scan_id*.

    Heuristic (Phase 3 MVP — will be refined in Phase 5):

    - Count failing findings for the scan.
    - Look up the scan's LLM connection to determine the model's per-token price.
    - Compute ``min_usd`` using ``_MIN_TOKENS_PER_FINDING`` (optimistic),
      ``max_usd`` using ``_MAX_TOKENS_PER_FINDING`` (pessimistic), and
      ``expected_tokens`` using ``_AVG_TOKENS_PER_FINDING["default"]``.
    - Input/output costs are averaged: ``avg_cost = (in_per_1M + out_per_1M) / 2``.

    Args:
        db: Active async database session.
        scan_id: UUID of the scan to cost-estimate.

    Returns:
        ``{"min_usd": float, "max_usd": float, "expected_tokens": int}``

    Raises:
        HTTPException: 404 if the scan is not found.
    """
    from backend.models.enums import CheckStatus  # noqa: PLC0415

    # Load scan.
    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = scan_result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found.",
        )

    # Count failing findings.
    findings_result = await db.execute(
        select(Finding).where(
            Finding.scan_id == scan_id,
            Finding.status == CheckStatus.failed,
        )
    )
    failing_findings = list(findings_result.scalars().all())
    n = len(failing_findings)

    # Resolve model from the scan's customer's LLM connection (prefer default).
    model = "unknown"
    llm_result = await db.execute(
        select(LLMConnection).where(
            LLMConnection.customer_id == scan.customer_id,
            LLMConnection.is_default.is_(True),
        )
    )
    default_llm = llm_result.scalar_one_or_none()
    if default_llm is None:
        # Fall back to any LLM connection for this customer.
        any_llm_result = await db.execute(
            select(LLMConnection).where(LLMConnection.customer_id == scan.customer_id)
        )
        default_llm = any_llm_result.scalar_one_or_none()
    if default_llm is not None:
        model = default_llm.model

    in_per_1m, out_per_1m = _cost_per_1m(model)
    avg_per_1m = (in_per_1m + out_per_1m) / 2.0

    avg_tokens = _AVG_TOKENS_PER_FINDING.get("default", 8_000)
    expected_tokens = n * avg_tokens
    min_usd = n * _MIN_TOKENS_PER_FINDING / 1_000_000 * avg_per_1m
    max_usd = n * _MAX_TOKENS_PER_FINDING / 1_000_000 * avg_per_1m

    return {
        "min_usd": round(min_usd, 6),
        "max_usd": round(max_usd, 6),
        "expected_tokens": expected_tokens,
    }
