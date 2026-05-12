"""Aggregate AgentRun performance metrics by (provider, model) — REQ-051."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun, RemediationAction
from backend.models.enums import AgentRunStatus, RemediationActionStatus
from backend.models.scan import Scan


@dataclass(frozen=True)
class ModelPerformanceMetrics:
    """Aggregate performance figures for a single (provider, model) pair.

    Attributes:
        provider: LLM provider string (e.g. ``"anthropic"``).
        model: Model identifier string (e.g. ``"claude-sonnet-4-6"``).
        run_count: Total number of agent runs for this pair.
        avg_cost_usd: Mean total cost per run in US dollars.
        avg_input_tokens: Mean total input tokens per run.
        avg_output_tokens: Mean total output tokens per run.
        success_rate: Fraction of runs with ``status == "completed"``.
        pr_open_rate: Fraction of runs that opened at least one PR
            (``RemediationAction.status == "opened"``).
        avg_runtime_seconds: Mean wall-clock runtime in seconds for runs that
            have both ``started_at`` and ``finished_at`` set; ``None`` when no
            completed-with-runtime runs exist.
        last_run_at: ``started_at`` timestamp of the most recent run in the
            group; ``None`` when no runs exist.
    """

    provider: str
    model: str
    run_count: int
    avg_cost_usd: float
    avg_input_tokens: float
    avg_output_tokens: float
    success_rate: float
    pr_open_rate: float
    avg_runtime_seconds: float | None
    last_run_at: datetime | None


async def compute_metrics(
    db: AsyncSession,
    *,
    customer_id: UUID | None = None,
    since: datetime | None = None,
) -> list[ModelPerformanceMetrics]:
    """Compute aggregate metrics over ``AgentRun`` rows grouped by (provider, model).

    This function is deliberately dialect-portable: runtime computation uses
    Python arithmetic on fetched ``datetime`` objects rather than
    ``func.extract("epoch", ...)`` which is PostgreSQL-specific and fails on
    the SQLite test database.

    Args:
        db: Async SQLAlchemy session.
        customer_id: When provided, only includes runs whose scan belongs to
            this customer (joined via ``Scan.customer_id``).
        since: When provided, only includes runs with ``started_at >= since``.

    Returns:
        A list of :class:`ModelPerformanceMetrics` instances ordered by
        ``run_count`` descending.
    """
    # ------------------------------------------------------------------
    # Phase 1: aggregate counts and token/cost averages per (provider, model)
    # ------------------------------------------------------------------
    stmt = (
        select(
            AgentRun.provider.label("provider"),
            AgentRun.model.label("model"),
            func.count(AgentRun.id).label("run_count"),
            func.avg(AgentRun.total_cost_usd).label("avg_cost_usd"),
            func.avg(AgentRun.total_input_tokens).label("avg_input_tokens"),
            func.avg(AgentRun.total_output_tokens).label("avg_output_tokens"),
            func.sum(
                case(
                    (AgentRun.status == AgentRunStatus.completed, 1),
                    else_=0,
                )
            ).label("completed_count"),
            func.max(AgentRun.started_at).label("last_run_at"),
        )
        .group_by(AgentRun.provider, AgentRun.model)
        .order_by(func.count(AgentRun.id).desc())
    )

    if customer_id is not None:
        stmt = stmt.join(Scan, AgentRun.scan_id == Scan.id).where(Scan.customer_id == customer_id)
    if since is not None:
        stmt = stmt.where(AgentRun.started_at >= since)

    rows = (await db.execute(stmt)).all()

    # ------------------------------------------------------------------
    # Phase 2: per-group supplemental queries and Python-side computation
    # ------------------------------------------------------------------
    metrics: list[ModelPerformanceMetrics] = []

    for row in rows:
        provider: str = row.provider
        model: str = row.model
        run_count = int(row.run_count)

        # PR open rate: distinct agent_run_ids that have >= 1 opened action.
        pr_stmt = (
            select(func.count(func.distinct(RemediationAction.agent_run_id)))
            .join(AgentRun, AgentRun.id == RemediationAction.agent_run_id)
            .where(
                AgentRun.provider == provider,
                AgentRun.model == model,
                RemediationAction.status == RemediationActionStatus.opened,
            )
        )
        if customer_id is not None:
            pr_stmt = pr_stmt.join(Scan, AgentRun.scan_id == Scan.id).where(
                Scan.customer_id == customer_id
            )
        if since is not None:
            pr_stmt = pr_stmt.where(AgentRun.started_at >= since)
        runs_with_open_pr = (await db.execute(pr_stmt)).scalar() or 0
        pr_open_rate = runs_with_open_pr / run_count if run_count else 0.0

        # Runtime: fetch (started_at, finished_at) pairs in Python to avoid
        # func.extract("epoch", ...) which is PostgreSQL-only.
        rt_stmt = select(AgentRun.started_at, AgentRun.finished_at).where(
            AgentRun.provider == provider,
            AgentRun.model == model,
            AgentRun.started_at.is_not(None),
            AgentRun.finished_at.is_not(None),
        )
        if customer_id is not None:
            rt_stmt = rt_stmt.join(Scan, AgentRun.scan_id == Scan.id).where(
                Scan.customer_id == customer_id
            )
        if since is not None:
            rt_stmt = rt_stmt.where(AgentRun.started_at >= since)

        rt_rows = (await db.execute(rt_stmt)).all()
        if rt_rows:
            runtimes = [(r.finished_at - r.started_at).total_seconds() for r in rt_rows]
            avg_runtime: float | None = sum(runtimes) / len(runtimes)
        else:
            avg_runtime = None

        success_rate = (int(row.completed_count or 0)) / run_count if run_count else 0.0

        metrics.append(
            ModelPerformanceMetrics(
                provider=provider,
                model=model,
                run_count=run_count,
                avg_cost_usd=float(row.avg_cost_usd or 0.0),
                avg_input_tokens=float(row.avg_input_tokens or 0.0),
                avg_output_tokens=float(row.avg_output_tokens or 0.0),
                success_rate=float(success_rate),
                pr_open_rate=float(pr_open_rate),
                avg_runtime_seconds=avg_runtime,
                last_run_at=row.last_run_at,
            )
        )

    return metrics
