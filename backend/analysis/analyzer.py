from __future__ import annotations

"""High-level orchestrator for the AI-powered DevOps analysis pipeline.

:class:`DevOpsAnalyzer` coordinates the full analysis workflow:

1. Accept scan results and category scores from the scanner pipeline.
2. Calculate benchmark alignment (DORA, OpenSSF, SLSA, CIS).
3. Hydrate the user-prompt template with all relevant data.
4. Invoke the :class:`~backend.analysis.client.AnalysisClient`.
5. Parse and validate the JSON response into an
   :class:`~backend.analysis.schemas.AnalysisResult`.
6. If any step fails, produce a graceful fallback result so the report
   pipeline can continue rather than crashing.

A module-level singleton :data:`analyzer` is created at import time using
the :data:`~backend.analysis.client.analysis_client` singleton.
"""

import json
import logging
from collections import defaultdict
from typing import Any

from pydantic import ValidationError

from backend.analysis.client import AnalysisClient, AnalysisClientError, analysis_client
from backend.analysis.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from backend.analysis.schemas import (
    AnalysisResult,
    BenchmarkComparison,
    CategoryNarrative,
    Recommendation,
)
from backend.benchmarks.cis import calculate_cis_compliance
from backend.benchmarks.dora import DORA_LEVELS, classify_dora_level
from backend.benchmarks.openssf import calculate_openssf_alignment
from backend.benchmarks.slsa import SLSA_LEVELS, calculate_slsa_level
from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult
from backend.scanners.orchestrator import CategoryScore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity ordering for display
# ---------------------------------------------------------------------------

_SEVERITY_ORDER: list[Severity] = [
    Severity.critical,
    Severity.high,
    Severity.medium,
    Severity.low,
    Severity.info,
]

# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class DevOpsAnalyzer:
    """Orchestrates the full AI analysis pipeline for a completed scan.

    Args:
        client: The :class:`~backend.analysis.client.AnalysisClient` to use
                for model calls.  Defaults to the module-level singleton when
                constructing :data:`analyzer`.

    Example::

        result = await analyzer.analyze_scan(
            org_name="Acme Corp",
            scan_results=check_results,
            category_scores=cat_scores,
            overall_score=73.5,
        )
    """

    def __init__(self, client: AnalysisClient) -> None:
        self._client: AnalysisClient = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_scan(
        self,
        org_name: str,
        scan_results: list[CheckResult],
        category_scores: dict[Category, CategoryScore],
        overall_score: float,
    ) -> AnalysisResult:
        """Run the complete AI analysis pipeline and return structured results.

        Steps performed:

        1. Extract the set of passed check IDs from *scan_results*.
        2. Compute DORA, OpenSSF, SLSA, and CIS benchmark data.
        3. Build the user prompt from the template.
        4. Inject the :class:`~backend.analysis.schemas.AnalysisResult` JSON
           schema into the prompt so the model knows the required output shape.
        5. Call the AI client.
        6. Strip any markdown fences and attempt JSON parsing + Pydantic
           validation.
        7. Return the validated :class:`~backend.analysis.schemas.AnalysisResult`
           or a fallback result if any step fails.

        Args:
            org_name:        Display name of the organisation being assessed.
            scan_results:    All :class:`~backend.scanners.base.CheckResult`
                             objects produced by the scanner pipeline.
            category_scores: Per-category scoring data keyed by
                             :class:`~backend.models.enums.Category`.
            overall_score:   The weighted overall score in ``[0.0, 100.0]``.

        Returns:
            A fully populated :class:`~backend.analysis.schemas.AnalysisResult`.
            Never raises — on failure a fallback result is returned.
        """
        # Step 1: Derive passed check IDs.
        passed_ids: set[str] = {
            r.check.check_id for r in scan_results if r.status is CheckStatus.passed
        }

        # Step 2: Compute benchmark alignment.
        dora_level: str = classify_dora_level(overall_score)
        openssf_alignment: dict[str, bool] = calculate_openssf_alignment(passed_ids)
        slsa_level: int = calculate_slsa_level(passed_ids)
        cis_compliance: dict[str, dict[str, Any]] = calculate_cis_compliance(passed_ids)

        # Step 3 & 4: Hydrate the user prompt.
        total_repos: int = len(
            {r.evidence.get("repo") for r in scan_results if r.evidence and "repo" in r.evidence}
        )
        # Use a safe fallback for total_repos when evidence doesn't carry repo keys.
        if total_repos == 0:
            total_repos = max(
                1,
                len(scan_results)
                // max(1, sum(cs.finding_count for cs in category_scores.values()) or 1),
            )

        json_schema: str = json.dumps(AnalysisResult.model_json_schema(), indent=2)

        user_prompt: str = USER_PROMPT_TEMPLATE.format(
            org_name=org_name,
            total_repos=total_repos,
            overall_score=f"{overall_score:.2f}",
            category_scores_table=self._format_category_scores(category_scores),
            failed_checks_summary=self._format_failed_checks(scan_results),
            passed_checks_summary=self._format_passed_checks(scan_results),
            benchmark_data=self._format_benchmark_data(
                dora_level=dora_level,
                openssf=openssf_alignment,
                slsa_level=slsa_level,
                cis=cis_compliance,
            ),
            json_schema=json_schema,
        )

        # Step 5: Call the AI client.
        try:
            raw_response: str = await self._client.analyze(
                prompt=user_prompt,
                system=SYSTEM_PROMPT,
            )
        except AnalysisClientError as exc:
            logger.warning(
                "DevOpsAnalyzer.analyze_scan: AI call failed — %s.  Returning fallback result.",
                exc,
            )
            return self._create_fallback_result(
                org_name=org_name,
                overall_score=overall_score,
                category_scores=category_scores,
                dora_level=dora_level,
                openssf=openssf_alignment,
                slsa_level=slsa_level,
                cis=cis_compliance,
                error_message=str(exc),
            )

        # Step 6: Parse and validate.
        try:
            result: AnalysisResult = self._parse_response(raw_response)
        except (ValueError, ValidationError) as exc:
            logger.warning(
                "DevOpsAnalyzer.analyze_scan: response parsing failed — %s.  "
                "Returning fallback result.",
                exc,
            )
            return self._create_fallback_result(
                org_name=org_name,
                overall_score=overall_score,
                category_scores=category_scores,
                dora_level=dora_level,
                openssf=openssf_alignment,
                slsa_level=slsa_level,
                cis=cis_compliance,
                error_message=str(exc),
            )

        logger.info(
            "DevOpsAnalyzer.analyze_scan: analysis complete for '%s' "
            "(%d recommendations, %d narratives).",
            org_name,
            len(result.recommendations),
            len(result.category_narratives),
        )
        return result

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_category_scores(
        self,
        scores: dict[Category, CategoryScore],
    ) -> str:
        """Render per-category scoring data as a plain-text table.

        Args:
            scores: Per-category scoring data.

        Returns:
            A multi-line string table with columns for category, score,
            percentage, pass count, and fail count.
        """
        header = f"{'Category':<20} {'Score':>8} {'Max':>8} {'%':>7} {'Passed':>8} {'Failed':>8}"
        separator = "-" * len(header)
        rows: list[str] = [header, separator]

        for cat in Category:
            if cat not in scores:
                continue
            cs = scores[cat]
            rows.append(
                f"{cat.value:<20} {cs.score:>8.2f} {cs.max_score:>8.2f} "
                f"{cs.percentage:>6.1f}% {cs.pass_count:>8d} {cs.fail_count:>8d}"
            )

        return "\n".join(rows)

    def _format_failed_checks(self, results: list[CheckResult]) -> str:
        """Render failed and warning checks grouped by severity.

        Args:
            results: All :class:`~backend.scanners.base.CheckResult` objects.

        Returns:
            A multi-line string listing each failing/warning check under its
            severity heading, including the check ID, name, category, and
            detail message.
        """
        # Group by severity — only failed, warning, error statuses.
        grouped: dict[Severity, list[CheckResult]] = defaultdict(list)
        for result in results:
            if result.status in (
                CheckStatus.failed,
                CheckStatus.warning,
                CheckStatus.error,
            ):
                grouped[result.check.severity].append(result)

        if not grouped:
            return "No failed or warning checks."

        lines: list[str] = []
        for severity in _SEVERITY_ORDER:
            items = grouped.get(severity)
            if not items:
                continue
            lines.append(f"\n### {severity.value.upper()} ({len(items)} checks)\n")
            for r in items:
                status_tag = f"[{r.status.value}]"
                lines.append(
                    f"  {status_tag:<10} {r.check.check_id:<12} "
                    f"{r.check.check_name} ({r.check.category.value})"
                )
                if r.detail:
                    lines.append(f"             Detail: {r.detail}")

        return "\n".join(lines)

    def _format_passed_checks(self, results: list[CheckResult]) -> str:
        """Render all passed checks as a plain-text list.

        Args:
            results: All :class:`~backend.scanners.base.CheckResult` objects.

        Returns:
            A multi-line string listing each passed check with its ID, name,
            and category.
        """
        passed = [r for r in results if r.status is CheckStatus.passed]

        if not passed:
            return "No checks passed."

        # Group by category for readability.
        grouped: dict[Category, list[CheckResult]] = defaultdict(list)
        for r in passed:
            grouped[r.check.category].append(r)

        lines: list[str] = [f"Total passed: {len(passed)}\n"]
        for cat in Category:
            items = grouped.get(cat)
            if not items:
                continue
            lines.append(f"\n### {cat.value.upper()} ({len(items)} passed)\n")
            for r in items:
                lines.append(f"  [PASS]     {r.check.check_id:<12} {r.check.check_name}")

        return "\n".join(lines)

    def _format_benchmark_data(
        self,
        dora_level: str,
        openssf: dict[str, bool],
        slsa_level: int,
        cis: dict[str, dict[str, Any]],
    ) -> str:
        """Render all benchmark framework results as formatted plain text.

        Args:
            dora_level:  The DORA performance level string (e.g. ``"high"``).
            openssf:     OpenSSF category-to-boolean alignment mapping.
            slsa_level:  Integer SLSA level achieved (0–3).
            cis:         CIS domain compliance breakdown.

        Returns:
            A multi-line string covering DORA, OpenSSF, SLSA, and CIS results.
        """
        lines: list[str] = []

        # ---- DORA -------------------------------------------------------
        dora_data = DORA_LEVELS.get(dora_level, {})
        lines.append("### DORA Metrics\n")
        lines.append(f"  Performance level : {dora_level.upper()}")
        lines.append(f"  Deployment freq.  : {dora_data.get('deployment_frequency', 'N/A')}")
        lines.append(f"  Lead time         : {dora_data.get('lead_time', 'N/A')}")
        lines.append(f"  Change failure    : {dora_data.get('change_failure_rate', 'N/A')}")
        lines.append(f"  MTTR              : {dora_data.get('mttr', 'N/A')}")
        lines.append(f"  Score threshold   : >= {dora_data.get('score_threshold', 'N/A')}")

        # ---- OpenSSF ----------------------------------------------------
        openssf_passed = [cat for cat, ok in openssf.items() if ok]
        openssf_failed = [cat for cat, ok in openssf.items() if not ok]
        lines.append("\n### OpenSSF Scorecard Alignment\n")
        lines.append(f"  Satisfied categories ({len(openssf_passed)}/{len(openssf)}):")
        for cat in openssf_passed:
            lines.append(f"    [PASS] {cat}")
        if openssf_failed:
            lines.append(f"\n  Unsatisfied categories ({len(openssf_failed)}):")
            for cat in openssf_failed:
                lines.append(f"    [FAIL] {cat}")

        # ---- SLSA -------------------------------------------------------
        lines.append("\n### SLSA Build Level\n")
        lines.append(f"  Achieved level: {slsa_level}")
        if slsa_level > 0:
            slsa_data = SLSA_LEVELS.get(slsa_level, {})
            lines.append(f"  Level name    : {slsa_data.get('name', 'N/A')}")
            lines.append(f"  Description   : {slsa_data.get('description', 'N/A')}")
        else:
            lines.append("  No SLSA level requirements currently satisfied.")

        # ---- CIS --------------------------------------------------------
        lines.append("\n### CIS Software Supply Chain Security\n")
        total_domains = len(cis)
        compliant_domains = sum(1 for d in cis.values() if d.get("compliant"))
        lines.append(f"  Compliant domains: {compliant_domains}/{total_domains}\n")
        for domain_id, domain_data in cis.items():
            status = "COMPLIANT" if domain_data.get("compliant") else "PARTIAL"
            pct = domain_data.get("percentage", 0)
            passed_count = domain_data.get("passed", 0)
            total_count = domain_data.get("total", 0)
            desc = domain_data.get("description", domain_id)
            lines.append(
                f"  [{status:<9}] {desc:<35} {passed_count}/{total_count} checks ({pct:.0f}%)"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str) -> AnalysisResult:
        """Parse the raw AI text response into an :class:`AnalysisResult`.

        The method strips any leading/trailing markdown code fences before
        attempting JSON parsing.  The parsed dict is then passed through
        Pydantic validation.

        Args:
            raw: The raw string returned by the model.

        Returns:
            A validated :class:`~backend.analysis.schemas.AnalysisResult`.

        Raises:
            ValueError: If the text cannot be decoded as JSON.
            :class:`pydantic.ValidationError`: If the JSON does not conform to
                the :class:`~backend.analysis.schemas.AnalysisResult` schema.
        """
        text = raw.strip()

        # Strip markdown code fences if present.
        if text.startswith("```"):
            # Remove the opening fence (and optional language tag).
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]

        text = text.strip()

        data: Any = json.loads(text)
        return AnalysisResult.model_validate(data)

    # ------------------------------------------------------------------
    # Fallback result
    # ------------------------------------------------------------------

    def _create_fallback_result(
        self,
        org_name: str,
        overall_score: float,
        category_scores: dict[Category, CategoryScore],
        dora_level: str,
        openssf: dict[str, bool],
        slsa_level: int,
        cis: dict[str, dict[str, Any]],
        error_message: str = "",
    ) -> AnalysisResult:
        """Construct a basic :class:`AnalysisResult` when the AI step fails.

        This fallback ensures the report generation pipeline always receives a
        valid result object regardless of AI availability.  The content is
        derived solely from the structured scan data and benchmark calculations
        — no AI content is included.

        Args:
            org_name:       Organisation display name.
            overall_score:  Weighted overall score.
            category_scores: Per-category scoring data.
            dora_level:     DORA performance level string.
            openssf:        OpenSSF category alignment mapping.
            slsa_level:     Integer SLSA level.
            cis:            CIS domain compliance data.
            error_message:  Description of the failure that triggered fallback.

        Returns:
            A minimal but structurally valid :class:`AnalysisResult`.
        """
        logger.info(
            "DevOpsAnalyzer._create_fallback_result: building fallback for '%s'.",
            org_name,
        )

        # Build category narratives from numeric data only.
        narratives: list[CategoryNarrative] = []
        for cat in Category:
            cs = category_scores.get(cat)
            if cs is None or cs.max_score == 0.0:
                continue
            pct = cs.percentage
            status_word = "strong" if pct >= 75 else "moderate" if pct >= 50 else "weak"
            narratives.append(
                CategoryNarrative(
                    category=cat.value,
                    score_percentage=round(pct, 2),
                    summary=(
                        f"{org_name} achieved a {pct:.1f}% score in the "
                        f"{cat.value} category, indicating a {status_word} "
                        f"posture.  {cs.pass_count} of {cs.finding_count} "
                        f"applicable checks passed."
                    ),
                    strengths=[f"{cs.pass_count} checks passed in this category."],
                    weaknesses=(
                        [f"{cs.fail_count} checks failed or raised warnings."]
                        if cs.fail_count > 0
                        else []
                    ),
                    key_findings=[
                        f"Score: {pct:.1f}% ({cs.score:.2f}/{cs.max_score:.2f})",
                        f"Pass: {cs.pass_count}, Fail: {cs.fail_count}",
                    ],
                )
            )

        # Build benchmark comparisons.
        openssf_passed_count = sum(1 for v in openssf.values() if v)
        openssf_total = len(openssf)
        dora_data = DORA_LEVELS.get(dora_level, {})

        cis_compliant = sum(1 for d in cis.values() if d.get("compliant"))
        cis_total = len(cis)

        benchmark_comparisons: list[BenchmarkComparison] = [
            BenchmarkComparison(
                framework="DORA",
                level_or_status=dora_level.upper(),
                summary=(
                    f"{org_name} is classified at the DORA {dora_level.upper()} "
                    f"performance level based on an overall score of "
                    f"{overall_score:.2f}/100."
                ),
                details={
                    "level": dora_level,
                    "deployment_frequency": dora_data.get("deployment_frequency", ""),
                    "lead_time": dora_data.get("lead_time", ""),
                    "change_failure_rate": dora_data.get("change_failure_rate", ""),
                    "mttr": dora_data.get("mttr", ""),
                    "score_threshold": dora_data.get("score_threshold", 0),
                },
            ),
            BenchmarkComparison(
                framework="OpenSSF",
                level_or_status=f"{openssf_passed_count}/{openssf_total} categories satisfied",
                summary=(
                    f"{org_name} satisfies {openssf_passed_count} of "
                    f"{openssf_total} OpenSSF Scorecard categories."
                ),
                details={cat: ok for cat, ok in openssf.items()},
            ),
            BenchmarkComparison(
                framework="SLSA",
                level_or_status=f"Level {slsa_level}",
                summary=(
                    f"{org_name} achieves SLSA Build Level {slsa_level} "
                    + (
                        f"({SLSA_LEVELS[slsa_level]['name']} — "
                        f"{SLSA_LEVELS[slsa_level]['description']})."
                        if slsa_level > 0
                        else "(no SLSA requirements currently satisfied)."
                    )
                ),
                details={
                    "level": slsa_level,
                    "name": SLSA_LEVELS[slsa_level]["name"] if slsa_level > 0 else "None",
                    "description": (
                        SLSA_LEVELS[slsa_level]["description"] if slsa_level > 0 else ""
                    ),
                },
            ),
            BenchmarkComparison(
                framework="CIS",
                level_or_status=f"{cis_compliant}/{cis_total} domains compliant",
                summary=(
                    f"{org_name} is fully compliant in {cis_compliant} of "
                    f"{cis_total} CIS Software Supply Chain Security domains."
                ),
                details={
                    domain_id: {
                        "description": str(d.get("description", domain_id)),
                        "passed": int(d.get("passed", 0)),
                        "total": int(d.get("total", 0)),
                        "percentage": float(d.get("percentage", 0.0)),
                        "compliant": bool(d.get("compliant", False)),
                    }
                    for domain_id, d in cis.items()
                },
            ),
        ]

        # Identify the lowest-scoring categories as risk highlights.
        sorted_cats = sorted(
            [cs for cs in category_scores.values() if cs.max_score > 0],
            key=lambda cs: cs.percentage,
        )
        risk_highlights: list[str] = [
            f"Low {cs.category.value} posture — score {cs.percentage:.1f}% "
            f"with {cs.fail_count} failed checks."
            for cs in sorted_cats[:5]
            if cs.percentage < 70
        ] or [
            f"Overall score of {overall_score:.2f}/100 indicates room for "
            f"improvement across DevOps practices."
        ]

        error_note = (
            (
                f"  Note: AI narrative generation was unavailable ({error_message}). "
                f"This report contains automatically generated content only."
            )
            if error_message
            else ""
        )

        return AnalysisResult(
            executive_summary=(
                f"{org_name} DevOps Assessment Summary\n\n"
                f"The automated assessment of {org_name} produced an overall "
                f"weighted score of {overall_score:.2f} out of 100, placing the "
                f"organisation at the DORA {dora_level.upper()} performance level.\n\n"
                f"The organisation achieved an OpenSSF alignment of "
                f"{openssf_passed_count}/{openssf_total} categories and SLSA Build "
                f"Level {slsa_level}.  CIS compliance stands at "
                f"{cis_compliant}/{cis_total} domains.\n\n"
                f"A detailed review of the findings below identifies key areas for "
                f"improvement and provides prioritised recommendations.\n"
                f"{error_note}"
            ),
            category_narratives=narratives,
            recommendations=[
                Recommendation(
                    priority=1,
                    title="Review and address all failed checks",
                    description=(
                        "A full list of failed checks is available in the findings "
                        "section.  Address critical and high severity items first to "
                        "achieve the greatest risk reduction."
                    ),
                    category="general",
                    effort="medium",
                    impact="high",
                    check_ids=[],
                )
            ],
            benchmark_comparisons=benchmark_comparisons,
            overall_maturity_assessment=(
                f"{org_name} currently operates at a DORA {dora_level.upper()} "
                f"performance level with an overall score of {overall_score:.2f}/100.  "
                f"Addressing the identified gaps — particularly in lower-scoring "
                f"categories — will improve the organisation's DevOps maturity and "
                f"security posture over the next 1–2 quarters."
            ),
            risk_highlights=risk_highlights,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

analyzer: DevOpsAnalyzer = DevOpsAnalyzer(client=analysis_client)
