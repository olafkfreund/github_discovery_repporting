from __future__ import annotations

"""Monthly cost-cap aggregator and enforcement for the remediation agent.

Aggregates ``AgentRun.total_cost_usd`` across all scans belonging to a
customer for the current calendar month (UTC) and compares the sum against
the cap stored in ``RemediationPolicy.max_cost_usd_per_month``.

Public surface:
  - ``compute_monthly_cost(db, customer_id, *, since)`` — raw aggregation.
  - ``get_cost_cap(db, customer_id)`` — policy look-up with safe default.
  - ``check(db, customer_id)`` — combined :class:`CostCapState` snapshot.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun
from backend.models.scan import Scan


@dataclass(frozen=True)
class CostCapState:
    """Per-customer monthly cost cap state at a point in time.

    Attributes:
        customer_id: UUID of the customer this state belongs to.
        month_start: First day of the current calendar month in UTC.
        spent_usd: Sum of ``AgentRun.total_cost_usd`` for this customer
            since ``month_start``.
        cap_usd: Monthly cap from ``RemediationPolicy``; default 100.0 if
            no policy row exists.
        remaining_usd: ``max(0.0, cap_usd - spent_usd)``.
        exceeded: ``True`` when ``spent_usd >= cap_usd``.
    """

    customer_id: UUID
    month_start: datetime
    spent_usd: float
    cap_usd: float
    remaining_usd: float
    exceeded: bool


def _month_start_utc(now: datetime | None = None) -> datetime:
    """Return the first day of the current calendar month in UTC.

    Args:
        now: Optional reference point; defaults to ``datetime.now(timezone.utc)``.

    Returns:
        A timezone-aware :class:`~datetime.datetime` at midnight UTC on the
        first day of the month containing *now*.
    """
    now = now or datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


async def compute_monthly_cost(
    db: AsyncSession,
    customer_id: UUID,
    *,
    since: datetime | None = None,
) -> float:
    """Return ``SUM(AgentRun.total_cost_usd)`` for *customer_id* since *since*.

    Joins ``agent_runs`` through ``scans`` to filter by customer.  Returns
    ``0.0`` when no rows match (e.g. no scans, no runs, or no runs in window).

    Args:
        db: Active async database session.
        customer_id: UUID of the customer whose agent-run costs to aggregate.
        since: Inclusive lower bound for ``AgentRun.created_at``.  Defaults to
            ``_month_start_utc()`` — i.e. the start of the current calendar
            month in UTC.

    Returns:
        Total LLM cost in USD as a Python :class:`float`.
    """
    if since is None:
        since = _month_start_utc()
    stmt = (
        select(func.coalesce(func.sum(AgentRun.total_cost_usd), 0.0))
        .join(Scan, AgentRun.scan_id == Scan.id)
        .where(Scan.customer_id == customer_id)
        .where(AgentRun.created_at >= since)
    )
    result = (await db.execute(stmt)).scalar()
    return float(result) if result is not None else 0.0


async def get_cost_cap(db: AsyncSession, customer_id: UUID) -> float:
    """Return the monthly cost cap for *customer_id*.

    Delegates to :func:`~backend.services.remediation_policy_service.get_for_customer`.
    Falls back to ``100.0`` — matching ``RemediationPolicy.max_cost_usd_per_month``
    server default — when no policy row exists.

    Args:
        db: Active async database session.
        customer_id: UUID of the customer whose policy to look up.

    Returns:
        Monthly cap in USD as a Python :class:`float`.
    """
    from backend.services import remediation_policy_service  # noqa: PLC0415

    policy = await remediation_policy_service.get_for_customer(db, customer_id)
    if policy is None:
        return 100.0
    return float(policy.max_cost_usd_per_month)


async def check(db: AsyncSession, customer_id: UUID) -> CostCapState:
    """Return the current :class:`CostCapState` for *customer_id*.

    Combines :func:`compute_monthly_cost` and :func:`get_cost_cap` into a
    single read-only snapshot.  Used by:

    - :func:`~backend.services.agent_service.create_agent_run` to reject runs
      that would exceed the cap.
    - ``GET /api/customers/{id}/cost-status`` to expose the state to the UI.

    Args:
        db: Active async database session.
        customer_id: UUID of the customer to evaluate.

    Returns:
        A frozen :class:`CostCapState` dataclass.
    """
    month_start = _month_start_utc()
    spent = await compute_monthly_cost(db, customer_id, since=month_start)
    cap = await get_cost_cap(db, customer_id)
    return CostCapState(
        customer_id=customer_id,
        month_start=month_start,
        spent_usd=spent,
        cap_usd=cap,
        remaining_usd=max(0.0, cap - spent),
        exceeded=spent >= cap,
    )
