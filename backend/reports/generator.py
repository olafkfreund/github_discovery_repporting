from __future__ import annotations

"""High-level report generation orchestration.

This module exposes a single :class:`ReportGenerator` class and a
module-level singleton :data:`report_generator` that the rest of the
application should import and reuse.

Typical usage::

    from backend.reports.generator import report_generator

    output_path = await report_generator.generate_report(
        scan_id=scan.id,
        customer_name="Acme Corp",
        org_name="acmecorp",
        analysis_result=analysis,
        category_scores=scores,
        overall_score=74.5,
        findings=check_results,
        dora_level="high",
    )
"""

import asyncio
import logging
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from backend.analysis.platform_context import get_platform_context
from backend.analysis.schemas import AnalysisResult
from backend.config import settings
from backend.models.enums import Category, Platform
from backend.reports.excel import ExcelRenderer
from backend.reports.markdown import MarkdownRenderer
from backend.reports.pdf import PDFRenderer
from backend.reports.zip_bundler import ZipBundler
from backend.scanners.base import CheckResult
from backend.scanners.orchestrator import CategoryScore

logger = logging.getLogger(__name__)

# Paths relative to this file — resolved once at import time.
_MODULE_DIR = Path(__file__).parent
_TEMPLATES_DIR = _MODULE_DIR / "templates"
_STYLES_DIR = _MODULE_DIR / "styles"


def _slugify(text: str) -> str:
    """Convert *text* to a filesystem-safe lowercase slug.

    Only ASCII alphanumerics and hyphens are kept; everything else is
    replaced with a hyphen and consecutive hyphens are collapsed.

    Parameters:
        text: Arbitrary string (e.g. a customer or organisation name).

    Returns:
        A normalised slug string.
    """
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "report"


def _build_findings_list(findings: list[CheckResult]) -> list[dict]:
    """Flatten :class:`~backend.scanners.base.CheckResult` objects to dicts.

    Each dict contains only the keys that the Jinja2 templates reference,
    keeping the template layer decoupled from the dataclass internals.

    Parameters:
        findings: Raw check results from the scanner orchestrator.

    Returns:
        List of plain dicts suitable for JSON serialisation or Jinja2
        template consumption.
    """
    return [
        {
            "check_id": r.check.check_id,
            "check_name": r.check.check_name,
            "category": r.check.category.value,
            "severity": r.check.severity.value,
            "status": r.status.value,
            "detail": r.detail,
            "score": r.score,
        }
        for r in findings
    ]


def _build_findings_by_category(
    findings_list: list[dict],
) -> dict[str, list[dict]]:
    """Group a flat findings list by category value.

    Parameters:
        findings_list: Output of :func:`_build_findings_list`.

    Returns:
        Mapping of category string to the subset of findings belonging to it.
    """
    result: dict[str, list[dict]] = {}
    for f in findings_list:
        result.setdefault(f["category"], []).append(f)
    return result


def _build_category_scores_dict(
    category_scores: dict[Category, CategoryScore],
) -> dict[str, float]:
    """Convert :class:`~backend.scanners.orchestrator.CategoryScore` objects
    to a plain ``{category_name: percentage}`` mapping.

    Parameters:
        category_scores: Output of
            :meth:`~backend.scanners.orchestrator.ScanOrchestrator.calculate_category_scores`.

    Returns:
        Ordered dict of ``{category_value: score_percentage}``.
    """
    return {
        cat.value: score.percentage
        for cat, score in category_scores.items()
        if score.max_score > 0.0
    }


class ReportGenerator:
    """Orchestrate the full PDF report generation pipeline.

    This class is responsible for:

    1. Transforming typed domain objects into the flat dictionary that the
       Jinja2 templates expect.
    2. Delegating HTML rendering and PDF conversion to :class:`PDFRenderer`.
    3. Persisting the generated PDF to the configured reports directory.

    The class is cheap to construct; instantiation only creates a
    :class:`PDFRenderer` and resolves a single output directory path.
    """

    def __init__(self) -> None:
        self._renderer = PDFRenderer(
            templates_dir=_TEMPLATES_DIR,
            styles_dir=_STYLES_DIR,
        )
        self._excel_renderer = ExcelRenderer()
        self._markdown_renderer = MarkdownRenderer()
        self._zip_bundler = ZipBundler()
        self._reports_dir = Path(settings.REPORTS_DIR).resolve()
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("ReportGenerator initialised; output dir=%s", self._reports_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_report(
        self,
        scan_id: UUID,
        customer_name: str,
        org_name: str,
        analysis_result: AnalysisResult,
        category_scores: dict[Category, CategoryScore],
        overall_score: float,
        findings: list[CheckResult],
        dora_level: str,
        platform: Platform = Platform.github,
    ) -> Path:
        """Generate a PDF report for a completed scan.

        This method is ``async`` to fit naturally into the async FastAPI
        request-handling context, even though the underlying WeasyPrint
        call is synchronous.  Callers that need true non-blocking behaviour
        should wrap this in ``asyncio.to_thread``.

        Parameters:
            scan_id: UUID of the completed scan — used in the filename.
            customer_name: Human-readable customer / company name for the
                cover page (e.g. ``"Acme Corp"``).
            org_name: Source-control organisation name (e.g. ``"acmecorp"``).
            analysis_result: Structured AI-analysis output — provides
                narratives, recommendations, benchmark comparisons, and
                risk highlights.
            category_scores: Per-category scoring data from the orchestrator.
            overall_score: Weighted overall score in the range [0.0, 100.0].
            findings: Full list of raw check results from the scanner
                orchestrator.
            dora_level: DORA maturity level string (e.g. ``"high"``).

        Returns:
            Resolved :class:`~pathlib.Path` to the generated PDF file.
        """
        logger.info(
            "Generating report for scan_id=%s org=%s score=%.2f",
            scan_id,
            org_name,
            overall_score,
        )

        # Build the flat data dict consumed by Jinja2 templates.
        findings_list = _build_findings_list(findings)
        report_data = self._build_report_data(
            scan_id=scan_id,
            customer_name=customer_name,
            org_name=org_name,
            analysis_result=analysis_result,
            category_scores=category_scores,
            overall_score=overall_score,
            findings_list=findings_list,
            dora_level=dora_level,
            platform=platform,
        )

        # Render HTML.
        html = self._renderer.render_report_html(report_data)

        # Determine output path.
        output_path = self._build_output_path(
            customer_name=customer_name,
            scan_id=scan_id,
        )

        # Write PDF in a thread to avoid blocking the async event loop
        # (WeasyPrint's rendering is synchronous and can take several seconds).
        result_path = await asyncio.to_thread(self._renderer.generate_pdf, html, output_path)

        logger.info("Report generated successfully: %s", result_path)
        return result_path

    async def generate_excel_report(
        self,
        scan_id: UUID,
        customer_name: str,
        org_name: str,
        analysis_result: AnalysisResult,
        category_scores: dict[Category, CategoryScore],
        overall_score: float,
        findings: list[CheckResult],
        dora_level: str,
        platform: Platform = Platform.github,
    ) -> Path:
        """Generate an Excel (.xlsx) report for a completed scan."""
        logger.info("Generating Excel report for scan_id=%s", scan_id)

        findings_list = _build_findings_list(findings)
        report_data = self._build_report_data(
            scan_id=scan_id,
            customer_name=customer_name,
            org_name=org_name,
            analysis_result=analysis_result,
            category_scores=category_scores,
            overall_score=overall_score,
            findings_list=findings_list,
            dora_level=dora_level,
            platform=platform,
        )

        output_path = self._build_output_path(
            customer_name=customer_name,
            scan_id=scan_id,
            extension=".xlsx",
        )

        result_path = await asyncio.to_thread(
            self._excel_renderer.generate_excel, report_data, output_path
        )
        logger.info("Excel report generated: %s", result_path)
        return result_path

    async def generate_zip_bundle(
        self,
        scan_id: UUID,
        customer_name: str,
        org_name: str,
        analysis_result: AnalysisResult,
        category_scores: dict[Category, CategoryScore],
        overall_score: float,
        findings: list[CheckResult],
        dora_level: str,
        platform: Platform = Platform.github,
    ) -> Path:
        """Generate a .zip bundle containing Excel and Markdown reports."""
        logger.info("Generating zip bundle for scan_id=%s", scan_id)

        findings_list = _build_findings_list(findings)
        report_data = self._build_report_data(
            scan_id=scan_id,
            customer_name=customer_name,
            org_name=org_name,
            analysis_result=analysis_result,
            category_scores=category_scores,
            overall_score=overall_score,
            findings_list=findings_list,
            dora_level=dora_level,
            platform=platform,
        )

        # Generate Excel into a temp location within the reports dir
        excel_path = self._build_output_path(
            customer_name=customer_name,
            scan_id=scan_id,
            extension=".xlsx",
            suffix="_bundle",
        )
        await asyncio.to_thread(self._excel_renderer.generate_excel, report_data, excel_path)

        # Generate Markdown into a subdirectory
        md_dir = self._reports_dir / f"_md_{_slugify(customer_name)}_{str(scan_id).split('-')[0]}"
        await asyncio.to_thread(self._markdown_renderer.generate_markdown, report_data, md_dir)

        # Bundle into zip
        zip_path = self._build_output_path(
            customer_name=customer_name,
            scan_id=scan_id,
            extension=".zip",
        )

        zip_files: list[tuple[Path, str]] = [
            (excel_path, "report.xlsx"),
            (md_dir, "markdown"),
        ]

        result_path = await asyncio.to_thread(self._zip_bundler.create_zip, zip_files, zip_path)

        # Clean up intermediate files
        excel_path.unlink(missing_ok=True)
        shutil.rmtree(md_dir, ignore_errors=True)

        logger.info("Zip bundle generated: %s", result_path)
        return result_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_report_data(
        self,
        *,
        scan_id: UUID,
        customer_name: str,
        org_name: str,
        analysis_result: AnalysisResult,
        category_scores: dict[Category, CategoryScore],
        overall_score: float,
        findings_list: list[dict],
        dora_level: str,
        platform: Platform = Platform.github,
    ) -> dict:
        """Assemble the complete template context dictionary.

        Returns:
            A flat dict whose keys correspond to variables referenced across
            all section templates.
        """
        now_utc = datetime.now(tz=UTC)
        generated_at = now_utc.strftime("%d %B %Y at %H:%M UTC")

        # Short scan identifier shown on the cover page.
        scan_id_short = str(scan_id).split("-")[0].upper()

        # Serialise Pydantic models to plain dicts for the templates.
        category_narratives = [n.model_dump() for n in analysis_result.category_narratives]
        recommendations = [r.model_dump() for r in analysis_result.recommendations]
        benchmark_comparisons = [b.model_dump() for b in analysis_result.benchmark_comparisons]

        platform_ctx = get_platform_context(platform)

        return {
            # Cover / header metadata
            "report_title": f"{platform_ctx['display_name']} DevOps Maturity Assessment — {org_name}",
            "customer_name": customer_name,
            "org_name": org_name,
            "scan_id": scan_id_short,
            "generated_at": generated_at,
            # Platform context
            "platform": platform.value,
            "platform_display_name": platform_ctx["display_name"],
            "platform_context": platform_ctx,
            # Scores
            "overall_score": overall_score,
            "dora_level": dora_level,
            "category_scores": _build_category_scores_dict(category_scores),
            # AI-generated narrative content
            "executive_summary": analysis_result.executive_summary,
            "overall_maturity": analysis_result.overall_maturity_assessment,
            "risk_highlights": analysis_result.risk_highlights,
            # Structured section data
            "category_narratives": category_narratives,
            "recommendations": recommendations,
            "benchmark_comparisons": benchmark_comparisons,
            # Findings (flat list + grouped by category)
            "all_findings": findings_list,
            "findings_by_category": _build_findings_by_category(findings_list),
        }

    def _build_output_path(
        self,
        *,
        customer_name: str,
        scan_id: UUID,
        extension: str = ".pdf",
        suffix: str = "",
    ) -> Path:
        """Build the output file path for a generated report artifact.

        Filename format::

            {customer_slug}_{scan_id_short}_{YYYYMMDD}{suffix}{extension}

        Parameters:
            customer_name: Human-readable customer name (will be slugified).
            scan_id: UUID for the scan (first segment used as short ID).
            extension: File extension including the dot (e.g. ".pdf", ".xlsx").
            suffix: Optional suffix before the extension (e.g. "_bundle").

        Returns:
            Full absolute path under :attr:`_reports_dir`.
        """
        customer_slug = _slugify(customer_name)
        scan_id_short = str(scan_id).split("-")[0].upper()
        date_str = datetime.now(tz=UTC).strftime("%Y%m%d")
        filename = f"{customer_slug}_{scan_id_short}_{date_str}{suffix}{extension}"
        return self._reports_dir / filename


# Module-level singleton — import this in the rest of the application.
report_generator = ReportGenerator()
