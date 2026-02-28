from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.models.customer import PlatformConnection
from backend.models.enums import ScanStatus
from backend.models.finding import Finding, ScanScore
from backend.models.scan import Scan, ScanRepo
from backend.providers.factory import create_provider
from backend.scanners.orchestrator import ScanOrchestrator

logger = logging.getLogger(__name__)


async def run_scan(scan_id: UUID, db_factory: async_sessionmaker) -> None:
    """Execute a full repository scan and persist all results.

    Opens its own database session from *db_factory* so it can run safely
    as an :func:`asyncio.create_task` background coroutine, independent of
    the HTTP request session that created the scan record.

    The pipeline is:

    1. Load the :class:`~backend.models.scan.Scan` and its
       :class:`~backend.models.customer.PlatformConnection`.
    2. Transition status to ``scanning`` and record ``started_at``.
    3. Build the platform provider from the connection's encrypted credentials.
    4. Fetch org-level assessment data and run org-level scanners.
    5. Enumerate all repositories visible to the provider.
    6. For every repository:

       a. Fetch assessment data from the provider.
       b. Persist a :class:`~backend.models.scan.ScanRepo` row.
       c. Run the :class:`~backend.scanners.orchestrator.ScanOrchestrator`
          against the assessment data.
       d. Persist a :class:`~backend.models.finding.Finding` row for every
          :class:`~backend.scanners.base.CheckResult`.

    7. Compute per-category scores via the orchestrator and persist
       :class:`~backend.models.finding.ScanScore` rows.
    8. Transition status to ``completed`` and record ``completed_at`` plus
       ``total_repos``.

    Any unhandled exception causes the scan to transition to ``failed`` with
    the exception message written to ``error_message``.  A final commit is
    issued in both the success and failure paths.

    Args:
        scan_id: Primary key of the :class:`~backend.models.scan.Scan` to run.
        db_factory: An :class:`~sqlalchemy.ext.asyncio.async_sessionmaker`
            used to open a fresh database session for the duration of this
            task.
    """
    async with db_factory() as session:
        await _execute_scan(scan_id, session)


async def _execute_scan(scan_id: UUID, session: AsyncSession) -> None:
    """Core scan logic scoped to a single *session*.

    Separated from :func:`run_scan` so that the session-management wrapper
    stays thin and this function remains straightforward to unit-test by
    passing a mock session directly.
    """
    # ------------------------------------------------------------------
    # Step 1: Load the Scan record together with its PlatformConnection.
    # ------------------------------------------------------------------
    result = await session.execute(
        select(Scan).where(Scan.id == scan_id).options(selectinload(Scan.connection))
    )
    scan: Scan | None = result.scalar_one_or_none()

    if scan is None:
        logger.error("run_scan: scan %s not found — aborting.", scan_id)
        return

    try:
        # ------------------------------------------------------------------
        # Step 2: Transition to "scanning".
        # ------------------------------------------------------------------
        scan.status = ScanStatus.scanning
        scan.started_at = datetime.now(tz=UTC)
        await session.commit()

        # ------------------------------------------------------------------
        # Step 3: Build the provider.
        # ------------------------------------------------------------------
        connection: PlatformConnection = scan.connection
        provider = create_provider(connection)

        orchestrator = ScanOrchestrator()

        # Accumulate all CheckResult objects across org + repos for scoring.
        from backend.scanners.base import CheckResult  # noqa: PLC0415

        all_results: list[CheckResult] = []

        # ------------------------------------------------------------------
        # Step 4: Org-level scanning phase (NEW).
        # ------------------------------------------------------------------
        try:
            org_data = await provider.get_org_assessment_data()
            org_results = orchestrator.scan_org(org_data)
            all_results.extend(org_results)

            # Persist org-level findings with scan_repo_id=None
            for check_result in org_results:
                finding = Finding(
                    scan_id=scan.id,
                    scan_repo_id=None,
                    category=check_result.check.category,
                    check_id=check_result.check.check_id,
                    check_name=check_result.check.check_name,
                    severity=check_result.check.severity,
                    status=check_result.status,
                    detail=check_result.detail or None,
                    evidence=check_result.evidence,
                    weight=check_result.check.weight,
                    score=check_result.score,
                )
                session.add(finding)

            await session.flush()
            logger.info(
                "run_scan: scan %s — %d org-level findings.",
                scan_id,
                len(org_results),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "run_scan: scan %s — org-level scanning failed (continuing with repo scanning)",
                scan_id,
            )

        # ------------------------------------------------------------------
        # Step 5: List all repositories.
        # ------------------------------------------------------------------
        repos = await provider.list_repos()
        logger.info("run_scan: scan %s — discovered %d repositories.", scan_id, len(repos))

        # ------------------------------------------------------------------
        # Step 6: Per-repository assessment.
        # ------------------------------------------------------------------
        for repo in repos:
            # a. Fetch assessment data.
            assessment = await provider.get_repo_assessment_data(repo)

            # b. Persist the ScanRepo record.
            scan_repo = ScanRepo(
                scan_id=scan.id,
                repo_external_id=repo.external_id,
                repo_name=repo.name,
                repo_url=repo.url,
                default_branch=repo.default_branch,
                raw_data=repo.model_dump(mode="json"),
            )
            session.add(scan_repo)
            # Flush so scan_repo.id is available for Finding foreign keys.
            await session.flush()

            # c. Run all repo-level scanners against the assessment data.
            results = orchestrator.scan_repo(assessment)
            all_results.extend(results)

            # d. Persist one Finding per CheckResult.
            for check_result in results:
                finding = Finding(
                    scan_id=scan.id,
                    scan_repo_id=scan_repo.id,
                    category=check_result.check.category,
                    check_id=check_result.check.check_id,
                    check_name=check_result.check.check_name,
                    severity=check_result.check.severity,
                    status=check_result.status,
                    detail=check_result.detail or None,
                    evidence=check_result.evidence,
                    weight=check_result.check.weight,
                    score=check_result.score,
                )
                session.add(finding)

        # Flush all findings before computing scores.
        await session.flush()

        # ------------------------------------------------------------------
        # Step 7: Compute category scores and persist ScanScore rows.
        # ------------------------------------------------------------------
        category_scores = orchestrator.calculate_category_scores(all_results)

        for cat_score in category_scores.values():
            scan_score = ScanScore(
                scan_id=scan.id,
                category=cat_score.category,
                score=cat_score.score,
                max_score=cat_score.max_score,
                weight=cat_score.weight,
                finding_count=cat_score.finding_count,
                pass_count=cat_score.pass_count,
                fail_count=cat_score.fail_count,
            )
            session.add(scan_score)

        # ------------------------------------------------------------------
        # Step 8: Mark scan completed.
        # ------------------------------------------------------------------
        scan.status = ScanStatus.completed
        scan.completed_at = datetime.now(tz=UTC)
        scan.total_repos = len(repos)

        logger.info(
            "run_scan: scan %s completed — %d repos, %d findings.",
            scan_id,
            len(repos),
            len(all_results),
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("run_scan: scan %s failed: %s", scan_id, exc)
        scan.status = ScanStatus.failed
        # Produce a user-friendly error for common failures.
        msg = str(exc)
        exc_type = type(exc).__name__
        if exc_type == "InvalidToken" or "InvalidToken" in msg:
            scan.error_message = (
                "Stored credentials could not be decrypted — the encryption key "
                "may have changed. Please edit this connection and re-enter your "
                "access token."
            )
        elif "401" in msg or "Unauthorized" in msg:
            scan.error_message = (
                "Authentication failed — the access token is invalid or expired. "
                "Please edit this connection and update the access token."
            )
        elif "403" in msg or "Forbidden" in msg:
            scan.error_message = (
                "Access denied — the token lacks the required scopes. "
                "Ensure it has read access to the organization/group and its repositories."
            )
        elif "404" in msg or "Not Found" in msg:
            scan.error_message = (
                f"Organization or group not found. Verify that '{connection.org_or_group}' "
                "is spelled correctly and the token has access to it."
            )
        else:
            scan.error_message = msg or f"{type(exc).__name__}: {exc!r}"

    finally:
        await session.commit()


def trigger_scan_background(scan_id: UUID) -> asyncio.Task:
    """Schedule :func:`run_scan` as a non-blocking asyncio background task.

    Retrieves the shared :data:`~backend.database.AsyncSessionLocal` factory
    from the database module and wraps :func:`run_scan` in an
    :func:`asyncio.create_task` call so the scan executes concurrently with
    the HTTP response being returned to the caller.

    Args:
        scan_id: Primary key of the scan to run in the background.

    Returns:
        The :class:`asyncio.Task` object (useful for testing / introspection).
    """
    from backend.database import AsyncSessionLocal  # noqa: PLC0415 — avoid import cycle

    logger.info("trigger_scan_background: scheduling scan %s.", scan_id)
    return asyncio.create_task(run_scan(scan_id, AsyncSessionLocal))
