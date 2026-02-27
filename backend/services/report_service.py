from __future__ import annotations

"""Background service that drives end-to-end report generation.

Entry points
------------
* :func:`generate_report_for_scan` — the async coroutine that performs the
  full pipeline (load data, analyse, generate PDF, persist results).
* :func:`trigger_report_generation` — fire-and-forget wrapper that schedules
  the above as an :mod:`asyncio` task so the HTTP request returns immediately.

Typical usage from the router::

    from backend.services.report_service import trigger_report_generation

    await db.commit()
    await db.refresh(report)
    trigger_report_generation(report.id)
    return ReportResponse.model_validate(report)
"""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.benchmarks.dora import classify_dora_level
from backend.config import settings
from backend.models.enums import Category, ReportStatus
from backend.models.finding import Finding, ScanScore
from backend.models.report import Report
from backend.models.scan import Scan
from backend.scanners.base import CheckResult, ScanCheck
from backend.scanners.orchestrator import CategoryScore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _reconstruct_check_results(findings: list[Finding]) -> list[CheckResult]:
    """Rebuild :class:`~backend.scanners.base.CheckResult` objects from DB rows.

    The scanner pipeline produces ``CheckResult`` dataclasses in memory; after
    they are persisted as :class:`~backend.models.finding.Finding` rows we need
    to reverse that transformation so the AI analyser receives the same typed
    objects it expects.

    Args:
        findings: All ``Finding`` ORM rows for the scan.

    Returns:
        A list of ``CheckResult`` instances with ``score`` auto-computed by
        ``CheckResult.__post_init__`` from the reconstructed status.
    """
    results: list[CheckResult] = []
    for finding in findings:
        check = ScanCheck(
            check_id=finding.check_id,
            check_name=finding.check_name,
            category=finding.category,
            severity=finding.severity,
            weight=finding.weight,
        )
        result = CheckResult(
            check=check,
            status=finding.status,
            detail=finding.detail or "",
            evidence=finding.evidence,
        )
        results.append(result)
    return results


def _reconstruct_category_scores(
    scan_scores: list[ScanScore],
) -> dict[Category, CategoryScore]:
    """Rebuild the :class:`~backend.scanners.orchestrator.CategoryScore` mapping.

    Args:
        scan_scores: All ``ScanScore`` ORM rows for the scan.

    Returns:
        A ``{Category: CategoryScore}`` dict identical in structure to what
        :meth:`~backend.scanners.orchestrator.ScanOrchestrator.calculate_category_scores`
        produces at scan time.
    """
    return {
        ss.category: CategoryScore(
            category=ss.category,
            score=ss.score,
            max_score=ss.max_score,
            weight=ss.weight,
            finding_count=ss.finding_count,
            pass_count=ss.pass_count,
            fail_count=ss.fail_count,
        )
        for ss in scan_scores
    }


def _calculate_overall_score(
    category_scores: dict[Category, CategoryScore],
) -> float:
    """Re-derive the weighted overall score from persisted category scores.

    Mirrors :meth:`~backend.scanners.orchestrator.ScanOrchestrator.calculate_overall_score`
    exactly so the value written to the ``Report`` row is consistent with what
    was computed during the original scan.

    Args:
        category_scores: Per-category scoring data.

    Returns:
        A float in ``[0.0, 100.0]`` rounded to two decimal places.
    """
    weighted_sum: float = 0.0
    total_weight: float = 0.0

    for cat_score in category_scores.values():
        if cat_score.max_score == 0.0:
            continue
        weighted_sum += cat_score.percentage * cat_score.weight
        total_weight += cat_score.weight

    if total_weight == 0.0:
        return 0.0

    return round(weighted_sum / total_weight, 2)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def generate_report_for_scan(
    report_id: UUID,
    db_factory: async_sessionmaker,
) -> None:
    """Drive the full report generation pipeline for a single report record.

    This coroutine is designed to run as a background :mod:`asyncio` task.  It
    opens its own database session so it is completely decoupled from the
    request/response session that created the ``Report`` row.

    Pipeline steps:

    1. Open a fresh async database session.
    2. Load the :class:`~backend.models.report.Report` together with its
       related :class:`~backend.models.scan.Scan`,
       :class:`~backend.models.customer.Customer`, and the scan's
       :class:`~backend.models.customer.PlatformConnection` (via
       ``selectinload``).
    3. Transition the report's ``status`` to ``"generating"`` and commit.
    4. Load all :class:`~backend.models.finding.Finding` rows for the scan.
    5. Load all :class:`~backend.models.finding.ScanScore` rows for the scan.
    6. Reconstruct in-memory :class:`~backend.scanners.base.CheckResult` objects
       from the ``Finding`` rows.
    7. Reconstruct the ``{Category: CategoryScore}`` mapping from ``ScanScore``
       rows.
    8. Derive the weighted ``overall_score`` from the category scores.
    9. Invoke the AI analyser to produce an
       :class:`~backend.analysis.schemas.AnalysisResult`.
    10. Invoke the PDF report generator.
    11. Persist ``ai_summary``, ``ai_recommendations``, ``overall_score``,
        ``dora_level``, ``pdf_path``, and ``status = "completed"`` to the
        ``Report`` row.
    12. On any unhandled exception: set ``status = "failed"``, log the error,
        and commit.

    Args:
        report_id:  UUID of the :class:`~backend.models.report.Report` record
                    to generate.
        db_factory: An :class:`~sqlalchemy.ext.asyncio.async_sessionmaker`
                    factory used to create the background session.  Pass
                    ``AsyncSessionLocal`` from :mod:`backend.database`.
    """
    async with db_factory() as db:
        try:
            # ------------------------------------------------------------------
            # Step 2: Load the Report with all required relationships.
            # ------------------------------------------------------------------
            stmt = (
                select(Report)
                .where(Report.id == report_id)
                .options(
                    selectinload(Report.scan).selectinload(Scan.connection),
                    selectinload(Report.customer),
                )
            )
            result = await db.execute(stmt)
            report = result.scalar_one_or_none()

            if report is None:
                logger.error(
                    "generate_report_for_scan: Report %s not found — aborting.",
                    report_id,
                )
                return

            scan = report.scan
            customer = report.customer
            connection = scan.connection

            # ------------------------------------------------------------------
            # Step 3: Transition to "generating".
            # ------------------------------------------------------------------
            report.status = ReportStatus.generating
            await db.commit()

            logger.info(
                "generate_report_for_scan: starting pipeline for report=%s "
                "scan=%s customer=%s org=%s",
                report_id,
                scan.id,
                customer.name,
                connection.org_or_group,
            )

            # ------------------------------------------------------------------
            # Step 4 & 5: Load findings and scores.
            # ------------------------------------------------------------------
            findings_result = await db.execute(
                select(Finding).where(Finding.scan_id == scan.id)
            )
            findings: list[Finding] = list(findings_result.scalars().all())

            scores_result = await db.execute(
                select(ScanScore).where(ScanScore.scan_id == scan.id)
            )
            scan_scores: list[ScanScore] = list(scores_result.scalars().all())

            # ------------------------------------------------------------------
            # Step 6 & 7: Reconstruct typed in-memory objects.
            # ------------------------------------------------------------------
            check_results = _reconstruct_check_results(findings)
            category_scores = _reconstruct_category_scores(scan_scores)

            # ------------------------------------------------------------------
            # Step 8: Derive overall score.
            # ------------------------------------------------------------------
            overall_score = _calculate_overall_score(category_scores)

            # ------------------------------------------------------------------
            # Step 9: Run AI analysis.
            # ------------------------------------------------------------------
            from backend.analysis.analyzer import (
                analyzer,  # lazy: avoids anthropic import at module level
            )

            analysis_result = await analyzer.analyze_scan(
                org_name=connection.org_or_group,
                scan_results=check_results,
                category_scores=category_scores,
                overall_score=overall_score,
            )

            # ------------------------------------------------------------------
            # Step 10: Generate PDF.
            # ------------------------------------------------------------------
            from backend.reports.generator import (
                report_generator,  # lazy: avoids weasyprint at module level
            )

            pdf_abs_path: Path = await report_generator.generate_report(
                scan_id=scan.id,
                customer_name=customer.name,
                org_name=connection.org_or_group,
                analysis_result=analysis_result,
                category_scores=category_scores,
                overall_score=overall_score,
                findings=check_results,
                dora_level=classify_dora_level(overall_score),
            )

            # Store the path relative to the configured reports directory so
            # the record remains portable across deployments.
            reports_root = Path(settings.REPORTS_DIR).resolve()
            try:
                pdf_relative = str(pdf_abs_path.relative_to(reports_root))
            except ValueError:
                # Fallback: store the absolute path if it falls outside the
                # configured root (e.g. during testing with temp directories).
                pdf_relative = str(pdf_abs_path)

            # ------------------------------------------------------------------
            # Step 11: Persist results.
            # ------------------------------------------------------------------
            report.ai_summary = analysis_result.executive_summary
            report.ai_recommendations = [
                r.model_dump() for r in analysis_result.recommendations
            ]
            report.overall_score = overall_score
            report.dora_level = classify_dora_level(overall_score)
            report.pdf_path = pdf_relative
            report.status = ReportStatus.completed

            await db.commit()

            logger.info(
                "generate_report_for_scan: completed report=%s pdf=%s",
                report_id,
                pdf_relative,
            )

        except Exception:
            # ------------------------------------------------------------------
            # Step 13: Error recovery — mark the report as failed.
            # ------------------------------------------------------------------
            logger.exception(
                "generate_report_for_scan: unhandled error for report=%s",
                report_id,
            )
            try:
                # Re-fetch to avoid working with a potentially stale/detached
                # instance after the exception.
                err_result = await db.execute(
                    select(Report).where(Report.id == report_id)
                )
                failed_report = err_result.scalar_one_or_none()
                if failed_report is not None:
                    failed_report.status = ReportStatus.failed
                    await db.commit()
            except Exception:
                logger.exception(
                    "generate_report_for_scan: could not persist failed "
                    "status for report=%s",
                    report_id,
                )


# ---------------------------------------------------------------------------
# Fire-and-forget entry point
# ---------------------------------------------------------------------------


def trigger_report_generation(report_id: UUID) -> None:
    """Schedule :func:`generate_report_for_scan` as a fire-and-forget task.

    This function is intentionally **not** ``async`` so it can be called from
    synchronous contexts inside endpoint handlers without ``await``.  It
    creates an :mod:`asyncio` task on the running event loop, which means the
    caller must be executing within an active event loop (always true inside a
    FastAPI handler).

    The :data:`~backend.database.AsyncSessionLocal` factory is imported lazily
    inside this function to avoid a circular-import at module load time.

    Args:
        report_id: UUID of the :class:`~backend.models.report.Report` row for
                   which generation should be triggered.
    """
    from backend.database import AsyncSessionLocal  # local import — avoids circular

    asyncio.ensure_future(
        generate_report_for_scan(
            report_id=report_id,
            db_factory=AsyncSessionLocal,
        )
    )
    logger.info(
        "trigger_report_generation: queued background task for report=%s",
        report_id,
    )
