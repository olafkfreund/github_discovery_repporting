from __future__ import annotations

"""Pydantic models that represent the structured output produced by the AI
analysis step.

These schemas serve two purposes:

1. They define the JSON structure that Claude is instructed to return so that
   the response can be validated and deserialized without ambiguity.
2. They provide a stable, typed contract between the :mod:`analysis` package
   and the rest of the application (report generation, API responses, etc.).
"""

from typing import Any

from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    """A single prioritised, actionable recommendation for the organisation.

    Attributes:
        priority:    Ordinal rank — ``1`` is the highest-priority item.  Lower
                     numbers should be addressed first.
        title:       Short imperative title (e.g. "Enable branch protection on
                     all default branches").
        description: Detailed description of the issue, its business impact,
                     and concrete remediation steps.
        category:    The DevOps category this recommendation belongs to
                     (e.g. ``"security"``, ``"cicd"``, ``"code_quality"``).
        effort:      Estimated implementation effort: ``"low"``, ``"medium"``,
                     or ``"high"``.
        impact:      Expected improvement to the overall posture if addressed:
                     ``"low"``, ``"medium"``, or ``"high"``.
        check_ids:   List of internal check IDs (e.g. ``["SEC-001", "SEC-002"]``)
                     that are directly related to this recommendation, allowing
                     consumers to cross-reference raw findings.
    """

    priority: int = Field(..., ge=1, description="Ordinal priority; 1 is highest.")
    title: str = Field(..., min_length=1, description="Short imperative title.")
    description: str = Field(..., min_length=1, description="Detailed remediation guidance.")
    category: str = Field(..., min_length=1, description="DevOps category label.")
    effort: str = Field(..., pattern=r"^(low|medium|high)$", description="Implementation effort level.")
    impact: str = Field(..., pattern=r"^(low|medium|high)$", description="Expected impact level if addressed.")
    check_ids: list[str] = Field(default_factory=list, description="Related scanner check IDs.")


class CategoryNarrative(BaseModel):
    """Human-readable narrative for a single DevOps category.

    Attributes:
        category:         The category identifier (e.g. ``"security"``).
        score_percentage: The numeric score for this category in the range
                          ``[0.0, 100.0]``.
        summary:          Two-to-three sentence prose overview of the
                          category's current state.
        strengths:        Bullet-style list of what the organisation is
                          doing well within this category.
        weaknesses:       Bullet-style list of gaps or areas requiring
                          improvement.
        key_findings:     The most significant individual findings (positive
                          or negative) surfaced during the scan.
    """

    category: str = Field(..., min_length=1, description="Category identifier.")
    score_percentage: float = Field(..., ge=0.0, le=100.0, description="Category score 0–100.")
    summary: str = Field(..., min_length=1, description="2–3 sentence prose summary.")
    strengths: list[str] = Field(default_factory=list, description="Positive findings.")
    weaknesses: list[str] = Field(default_factory=list, description="Gap areas.")
    key_findings: list[str] = Field(default_factory=list, description="Most significant findings.")


class BenchmarkComparison(BaseModel):
    """Structured alignment data for a single industry benchmark or framework.

    Attributes:
        framework:       The benchmark name: ``"DORA"``, ``"OpenSSF"``,
                         ``"SLSA"``, or ``"CIS"``.
        level_or_status: The level or compliance status achieved — for
                         example ``"high"`` (DORA), ``"Level 2"`` (SLSA),
                         or ``"Partial"`` (CIS).
        summary:         One-to-two sentence prose contextualising the
                         result against industry norms.
        details:         Framework-specific detail payload (e.g. individual
                         DORA metric descriptions, OpenSSF category pass/fail
                         mapping, CIS domain breakdown).
    """

    framework: str = Field(..., description="Benchmark framework name.")
    level_or_status: str = Field(..., description="Achieved level or compliance status.")
    summary: str = Field(..., min_length=1, description="Contextual summary.")
    details: dict[str, Any] = Field(default_factory=dict, description="Framework-specific details.")


class AnalysisResult(BaseModel):
    """Top-level container for the complete AI-generated assessment output.

    This model is the single artefact returned by
    :meth:`~backend.analysis.analyzer.DevOpsAnalyzer.analyze_scan` and is
    intended to be serialised into the generated PDF/HTML report.

    Attributes:
        executive_summary:          Three-to-five paragraph executive
                                    summary suitable for a C-suite audience.
                                    Should cover overall posture, key risks,
                                    and the recommended path forward.
        category_narratives:        One :class:`CategoryNarrative` per
                                    assessed category, ordered by category
                                    importance.
        recommendations:            All actionable recommendations ordered
                                    ascending by :attr:`Recommendation.priority`
                                    (item 1 first).
        benchmark_comparisons:      One :class:`BenchmarkComparison` per
                                    assessed framework (DORA, OpenSSF, SLSA,
                                    CIS).
        overall_maturity_assessment: One-to-two paragraph statement of the
                                    organisation's overall DevOps maturity
                                    level and trajectory.
        risk_highlights:            Three-to-five concise risk statements
                                    surfacing the most critical security or
                                    operational threats.
    """

    executive_summary: str = Field(..., min_length=1, description="3–5 paragraph executive summary.")
    category_narratives: list[CategoryNarrative] = Field(
        default_factory=list,
        description="Per-category narratives.",
    )
    recommendations: list[Recommendation] = Field(
        default_factory=list,
        description="Ordered recommendations (priority 1 first).",
    )
    benchmark_comparisons: list[BenchmarkComparison] = Field(
        default_factory=list,
        description="Industry benchmark alignment data.",
    )
    overall_maturity_assessment: str = Field(
        ...,
        min_length=1,
        description="1–2 paragraph overall maturity statement.",
    )
    risk_highlights: list[str] = Field(
        default_factory=list,
        description="Top 3–5 critical risk items.",
    )
