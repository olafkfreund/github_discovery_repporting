from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.report import Report, ReportTemplate
from backend.models.scan import Scan
from backend.schemas.report import (
    ReportCreate,
    ReportDetailResponse,
    ReportResponse,
    TemplateCreate,
    TemplateResponse,
)
from backend.services import customer_service
from backend.services.report_service import trigger_report_generation

router = APIRouter(tags=["reports"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_report_or_404(db: AsyncSession, report_id: UUID) -> Report:
    """Fetch a :class:`~backend.models.report.Report` by primary key or raise 404.

    Args:
        db: An active async database session.
        report_id: UUID of the target report.

    Returns:
        The ``Report`` ORM instance.

    Raises:
        HTTPException: 404 if no report with the given ID exists.
    """
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found.",
        )
    return report


async def _get_template_or_404(db: AsyncSession, template_id: UUID) -> ReportTemplate:
    """Fetch a :class:`~backend.models.report.ReportTemplate` or raise 404.

    Args:
        db: An active async database session.
        template_id: UUID of the target template.

    Returns:
        The ``ReportTemplate`` ORM instance.

    Raises:
        HTTPException: 404 if no template with the given ID exists.
    """
    result = await db.execute(
        select(ReportTemplate).where(ReportTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found.",
        )
    return template


# ---------------------------------------------------------------------------
# Report endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/scans/{scan_id}/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a report request for a scan",
)
async def create_report(
    scan_id: UUID,
    payload: ReportCreate,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Create a report record in ``pending`` status.

    Actual PDF generation runs as a background task in Phase 3.  This
    endpoint returns immediately after persisting the report record.

    The ``scan_id`` from the URL path takes precedence over any ``scan_id``
    in the request body.

    Args:
        scan_id: UUID of the scan to report on.
        payload: Report creation payload with optional title and template.
        db: Injected async database session.

    Returns:
        The newly created report record with ``status="pending"``.

    Raises:
        HTTPException: 404 if the scan or referenced template does not exist.
    """
    # Verify the scan exists.
    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = scan_result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found.",
        )

    # Verify the template if one was supplied.
    if payload.template_id is not None:
        await _get_template_or_404(db, payload.template_id)

    title = payload.title or f"DevOps Assessment Report – Scan {scan_id}"

    report = Report(
        scan_id=scan_id,
        customer_id=scan.customer_id,
        template_id=payload.template_id,
        title=title,
        generated_at=datetime.now(tz=UTC),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    trigger_report_generation(report.id)
    return ReportResponse.model_validate(report)


@router.get(
    "/reports/{report_id}",
    response_model=ReportDetailResponse,
    summary="Get a report by ID",
)
async def get_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ReportDetailResponse:
    """Fetch the full report record including AI-generated content.

    Args:
        report_id: UUID of the target report.
        db: Injected async database session.

    Returns:
        The full report detail record.

    Raises:
        HTTPException: 404 if no report with the given ID exists.
    """
    report = await _get_report_or_404(db, report_id)
    return ReportDetailResponse.model_validate(report)


@router.get(
    "/reports/{report_id}/download",
    summary="Download a report PDF",
    response_class=FileResponse,
)
async def download_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Stream the generated PDF for a completed report.

    Args:
        report_id: UUID of the target report.
        db: Injected async database session.

    Returns:
        The PDF file as a streaming ``FileResponse``.

    Raises:
        HTTPException: 404 if the report does not exist or has no PDF yet.
    """
    report = await _get_report_or_404(db, report_id)
    if not report.pdf_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} has no PDF available yet.",
        )

    pdf_path = Path(report.pdf_path)
    if not pdf_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"PDF file for report {report_id} was recorded but is missing "
                "from the filesystem."
            ),
        )

    filename = pdf_path.name
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
    )


@router.get(
    "/customers/{customer_id}/reports",
    response_model=list[ReportResponse],
    summary="List reports for a customer",
)
async def list_customer_reports(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ReportResponse]:
    """Return all reports belonging to a customer, ordered newest first.

    Args:
        customer_id: UUID of the owning customer.
        db: Injected async database session.

    Returns:
        A list of report records, possibly empty.

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
        select(Report)
        .where(Report.customer_id == customer_id)
        .order_by(Report.created_at.desc())
    )
    reports = list(result.scalars().all())
    return [ReportResponse.model_validate(r) for r in reports]


# ---------------------------------------------------------------------------
# Template endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/templates",
    response_model=list[TemplateResponse],
    summary="List report templates",
)
async def list_templates(
    db: AsyncSession = Depends(get_db),
) -> list[TemplateResponse]:
    """Return all available report templates ordered by name.

    Args:
        db: Injected async database session.

    Returns:
        A list of template records, possibly empty.
    """
    result = await db.execute(
        select(ReportTemplate).order_by(ReportTemplate.name)
    )
    templates = list(result.scalars().all())
    return [TemplateResponse.model_validate(t) for t in templates]


@router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a report template",
)
async def create_template(
    payload: TemplateCreate,
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Create and persist a new report template.

    Args:
        payload: Template creation payload.
        db: Injected async database session.

    Returns:
        The newly created template record.
    """
    template = ReportTemplate(
        name=payload.name,
        description=payload.description,
        is_default=payload.is_default,
        header_logo_path=payload.header_logo_path,
        accent_color=payload.accent_color,
        include_sections=payload.include_sections,
        custom_css=payload.custom_css,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return TemplateResponse.model_validate(template)


@router.put(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Update a report template",
)
async def update_template(
    template_id: UUID,
    payload: TemplateCreate,
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Replace all mutable fields on an existing report template.

    ``TemplateCreate`` is reused here because all fields should be re-supplied
    on an update (full replacement semantics).

    Args:
        template_id: UUID of the template to update.
        payload: Full replacement payload.
        db: Injected async database session.

    Returns:
        The updated template record.

    Raises:
        HTTPException: 404 if no template with the given ID exists.
    """
    template = await _get_template_or_404(db, template_id)

    template.name = payload.name
    template.description = payload.description
    template.is_default = payload.is_default
    template.header_logo_path = payload.header_logo_path
    template.accent_color = payload.accent_color
    template.include_sections = payload.include_sections
    template.custom_css = payload.custom_css

    await db.commit()
    await db.refresh(template)
    return TemplateResponse.model_validate(template)
