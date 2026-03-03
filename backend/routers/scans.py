from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.customer import PlatformConnection
from backend.models.enums import Category, CheckStatus, ScanStatus, Severity
from backend.models.finding import Finding, ScanScore
from backend.models.scan import Scan
from backend.schemas.finding import FindingResponse
from backend.schemas.scan import ScanCreate, ScanResponse, ScanScoreResponse
from backend.services import customer_service
from backend.services.scan_service import trigger_scan_background

router = APIRouter(tags=["scans"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_scan_or_404(db: AsyncSession, scan_id: UUID) -> Scan:
    """Fetch a :class:`~backend.models.scan.Scan` by primary key or raise 404.

    Args:
        db: An active async database session.
        scan_id: UUID of the target scan.

    Returns:
        The ``Scan`` ORM instance.

    Raises:
        HTTPException: 404 if no scan with the given ID exists.
    """
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found.",
        )
    return scan


# ---------------------------------------------------------------------------
# Scan endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/customers/{customer_id}/scans",
    response_model=ScanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger a new scan for a customer",
)
async def trigger_scan(
    customer_id: UUID,
    payload: ScanCreate,
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """Create a new scan record in ``pending`` status.

    The actual scanning work runs as a background task in Phase 2.  This
    endpoint returns immediately after persisting the scan record.

    Args:
        customer_id: UUID of the owning customer.
        payload: Scan creation payload including the target connection ID and
            optional configuration.
        db: Injected async database session.

    Returns:
        The newly created scan record with ``status="pending"``.

    Raises:
        HTTPException: 404 if the customer or the referenced connection does
            not exist, or if the connection does not belong to this customer.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    # Verify the connection exists and belongs to this customer.
    conn_result = await db.execute(
        select(PlatformConnection).where(
            PlatformConnection.id == payload.connection_id,
            PlatformConnection.customer_id == customer_id,
        )
    )
    connection = conn_result.scalar_one_or_none()
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Connection {payload.connection_id} not found "
                f"for customer {customer_id}."
            ),
        )

    scan = Scan(
        customer_id=customer_id,
        connection_id=payload.connection_id,
        status=ScanStatus.pending,
        scan_config=payload.scan_config,
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    # Fire the scan pipeline as a non-blocking background task so the HTTP
    # response is returned immediately while the scan runs concurrently.
    trigger_scan_background(scan.id)

    return ScanResponse.model_validate(scan)


@router.get(
    "/customers/{customer_id}/scans",
    response_model=list[ScanResponse],
    summary="List scans for a customer",
)
async def list_customer_scans(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ScanResponse]:
    """Return all scans belonging to a customer, ordered by creation time (newest first).

    Args:
        customer_id: UUID of the owning customer.
        db: Injected async database session.

    Returns:
        A list of scan records, possibly empty.

    Raises:
        HTTPException: 404 if the customer does not exist.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    result = await db.execute(
        select(Scan)
        .where(Scan.customer_id == customer_id)
        .order_by(Scan.created_at.desc())
    )
    scans = list(result.scalars().all())
    return [ScanResponse.model_validate(s) for s in scans]


@router.get(
    "/scans/{scan_id}",
    response_model=ScanResponse,
    summary="Get a scan by ID",
)
async def get_scan(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """Fetch a single scan by primary key.

    Args:
        scan_id: UUID of the target scan.
        db: Injected async database session.

    Returns:
        The scan record.

    Raises:
        HTTPException: 404 if no scan with the given ID exists.
    """
    scan = await _get_scan_or_404(db, scan_id)
    return ScanResponse.model_validate(scan)


@router.get(
    "/scans/{scan_id}/findings",
    response_model=list[FindingResponse],
    summary="List findings for a scan",
)
async def list_scan_findings(
    scan_id: UUID,
    category: Category | None = Query(default=None),
    severity: Severity | None = Query(default=None),
    check_status: CheckStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[FindingResponse]:
    """Return findings recorded during a scan, with optional filtering.

    All filter parameters are optional.  Omitting a parameter means no
    filtering on that dimension.

    Args:
        scan_id: UUID of the parent scan.
        category: Optional category filter (e.g. ``security``, ``cicd``).
        severity: Optional severity filter (e.g. ``critical``, ``high``).
        check_status: Optional status filter (e.g. ``failed``, ``passed``).
            Passed as the ``status`` query parameter.
        db: Injected async database session.

    Returns:
        A filtered list of finding records, possibly empty.

    Raises:
        HTTPException: 404 if no scan with the given ID exists.
    """
    await _get_scan_or_404(db, scan_id)

    query = select(Finding).where(Finding.scan_id == scan_id)

    if category is not None:
        query = query.where(Finding.category == category)
    if severity is not None:
        query = query.where(Finding.severity == severity)
    if check_status is not None:
        query = query.where(Finding.status == check_status)

    result = await db.execute(query.order_by(Finding.severity, Finding.check_name))
    findings = list(result.scalars().all())
    return [FindingResponse.model_validate(f) for f in findings]


@router.get(
    "/scans/{scan_id}/scores",
    response_model=list[ScanScoreResponse],
    summary="Get category scores for a scan",
)
async def list_scan_scores(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ScanScoreResponse]:
    """Return aggregated category scores for a completed scan.

    Args:
        scan_id: UUID of the parent scan.
        db: Injected async database session.

    Returns:
        A list of category score records, possibly empty.

    Raises:
        HTTPException: 404 if no scan with the given ID exists.
    """
    await _get_scan_or_404(db, scan_id)

    result = await db.execute(
        select(ScanScore)
        .where(ScanScore.scan_id == scan_id)
        .order_by(ScanScore.category)
    )
    scores = list(result.scalars().all())
    return [ScanScoreResponse.model_validate(s) for s in scores]
