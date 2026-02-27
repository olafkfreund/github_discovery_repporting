from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.customer import Customer
from backend.models.report import Report
from backend.models.scan import Scan
from backend.schemas.scan import ScanResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Number of days to look back when counting "recent" scans.
_RECENT_DAYS: int = 30

# Number of scans to surface in the recent-scans endpoint.
_RECENT_SCANS_LIMIT: int = 10


@router.get(
    "/stats",
    summary="Overall platform statistics",
)
async def get_stats(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return aggregate counts across the whole platform.

    The ``recent_scan_count`` value reflects scans created in the last
    ``30`` calendar days.

    Args:
        db: Injected async database session.

    Returns:
        A dict with the following keys:

        * ``total_customers`` – total number of customer records.
        * ``total_scans`` – total number of scan records.
        * ``total_reports`` – total number of report records.
        * ``recent_scan_count`` – scans created in the last 30 days.
    """
    # Run all four aggregate queries concurrently via individual awaits.
    # (SQLAlchemy async sessions are not thread-safe for true concurrency, so
    # we issue them sequentially but keep the code clean.)

    total_customers_result = await db.execute(
        select(func.count()).select_from(Customer)
    )
    total_customers: int = total_customers_result.scalar_one()

    total_scans_result = await db.execute(select(func.count()).select_from(Scan))
    total_scans: int = total_scans_result.scalar_one()

    total_reports_result = await db.execute(select(func.count()).select_from(Report))
    total_reports: int = total_reports_result.scalar_one()

    cutoff = datetime.now(tz=UTC) - timedelta(days=_RECENT_DAYS)
    recent_scan_result = await db.execute(
        select(func.count())
        .select_from(Scan)
        .where(Scan.created_at >= cutoff)
    )
    recent_scan_count: int = recent_scan_result.scalar_one()

    return {
        "total_customers": total_customers,
        "total_scans": total_scans,
        "total_reports": total_reports,
        "recent_scan_count": recent_scan_count,
    }


@router.get(
    "/recent-scans",
    response_model=list[ScanResponse],
    summary="Most recent scans across all customers",
)
async def get_recent_scans(
    db: AsyncSession = Depends(get_db),
) -> list[ScanResponse]:
    """Return the ten most recently created scans across all customers.

    Args:
        db: Injected async database session.

    Returns:
        Up to 10 scan records ordered newest first.
    """
    result = await db.execute(
        select(Scan)
        .order_by(Scan.created_at.desc())
        .limit(_RECENT_SCANS_LIMIT)
    )
    scans = list(result.scalars().all())
    return [ScanResponse.model_validate(s) for s in scans]
