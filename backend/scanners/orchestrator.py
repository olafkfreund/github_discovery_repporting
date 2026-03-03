from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.models.enums import Category, CheckStatus
from backend.scanners.base import BaseScanner, CheckResult, OrgScanner, Scanner
from backend.scanners.cicd import CICDScanner
from backend.scanners.code_quality import CodeQualityScanner
from backend.scanners.collaboration import CollaborationScanner
from backend.scanners.compliance import ComplianceScanner
from backend.scanners.container_security import ContainerSecurityScanner
from backend.scanners.dast import DASTScanner
from backend.scanners.dependencies import DependenciesScanner
from backend.scanners.disaster_recovery import DisasterRecoveryScanner
from backend.scanners.identity_access import IdentityAccessScanner
from backend.scanners.migration import MigrationScanner
from backend.scanners.monitoring import MonitoringScanner
from backend.scanners.platform_arch import PlatformArchScanner
from backend.scanners.repo_governance import RepoGovernanceScanner
from backend.scanners.sast import SASTScanner
from backend.scanners.sdlc_process import SDLCProcessScanner
from backend.scanners.secrets_mgmt import SecretsMgmtScanner
from backend.schemas.platform_data import OrgAssessmentData, RepoAssessmentData


@dataclass
class CategoryScore:
    """Aggregated scoring data for a single :class:`~backend.models.enums.Category`.

    Attributes:
        category:      The category being scored.
        score:         Sum of earned scores across all checks in this category.
        max_score:     Maximum possible score (sum of all check weights).
        weight:        Category-level weight used in the overall weighted average.
        finding_count: Total number of check results evaluated.
        pass_count:    Number of checks that passed.
        fail_count:    Number of checks that failed or errored.
    """

    category: Category
    score: float
    max_score: float
    weight: float
    finding_count: int
    pass_count: int
    fail_count: int

    @property
    def percentage(self) -> float:
        """Percentage score for this category (0-100).

        Returns 0.0 when *max_score* is zero to avoid division by zero.
        """
        if self.max_score == 0.0:
            return 0.0
        return (self.score / self.max_score) * 100.0


def _category_key(scanner: OrgScanner | Scanner) -> str:
    """Return the string key for a scanner's category."""
    cat = scanner.category
    return cat.value if isinstance(cat, Category) else str(cat)


class ScanOrchestrator:
    """Coordinates all 16 scanner instances and produces a unified assessment.

    When *scan_config* is provided, the orchestrator filters out disabled
    categories/checks, overrides category weights, and injects per-check
    threshold configuration into each scanner.

    Usage::

        orchestrator = ScanOrchestrator(scan_config=scan.scan_config)

        # Org-level scanning
        org_results = orchestrator.scan_org(org_data)

        # Repo-level scanning
        repo_results = orchestrator.scan_repo(repo_data)

        # Combine and score
        all_results = org_results + repo_results
        category_scores = orchestrator.calculate_category_scores(all_results)
        overall = orchestrator.calculate_overall_score(category_scores)
    """

    def __init__(self, scan_config: dict[str, Any] | None = None) -> None:
        # Instantiate all scanners first.
        all_org: list[OrgScanner] = [
            PlatformArchScanner(),
            IdentityAccessScanner(),
        ]
        all_repo: list[Scanner] = [
            RepoGovernanceScanner(),
            CICDScanner(),
            SecretsMgmtScanner(),
            DependenciesScanner(),
            SASTScanner(),
            DASTScanner(),
            ContainerSecurityScanner(),
            CodeQualityScanner(),
            SDLCProcessScanner(),
            ComplianceScanner(),
            CollaborationScanner(),
            DisasterRecoveryScanner(),
            MonitoringScanner(),
            MigrationScanner(),
        ]

        self._disabled_checks: set[str] = set()

        categories_cfg: dict[str, Any] = {}
        if scan_config:
            categories_cfg = scan_config.get("categories", {})

        # Apply per-category config: enable/disable, weight override, check config.
        self._org_scanners: list[OrgScanner] = []
        for scanner in all_org:
            cat_key = _category_key(scanner)
            cat_cfg = categories_cfg.get(cat_key, {})
            if cat_cfg.get("enabled", True) is False:
                continue
            if "weight" in cat_cfg:
                scanner.weight = float(cat_cfg["weight"])
            self._apply_check_config(scanner, cat_cfg)
            self._org_scanners.append(scanner)

        self._repo_scanners: list[Scanner] = []
        for repo_scanner in all_repo:
            cat_key = _category_key(repo_scanner)
            cat_cfg = categories_cfg.get(cat_key, {})
            if cat_cfg.get("enabled", True) is False:
                continue
            if "weight" in cat_cfg:
                repo_scanner.weight = float(cat_cfg["weight"])
            self._apply_check_config(repo_scanner, cat_cfg)
            self._repo_scanners.append(repo_scanner)

        # Renormalise weights so enabled scanners sum to 1.0.
        if categories_cfg:
            self._renormalise_weights()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_check_config(
        self, scanner: OrgScanner | Scanner, cat_cfg: dict[str, Any]
    ) -> None:
        """Inject check-level config (thresholds, disable flags) into a scanner."""
        checks_cfg: dict[str, Any] = cat_cfg.get("checks", {})
        if isinstance(scanner, BaseScanner):
            scanner._check_config = checks_cfg
        # Collect individually disabled checks.
        for check_id, check_cfg in checks_cfg.items():
            if isinstance(check_cfg, dict) and check_cfg.get("enabled", True) is False:
                self._disabled_checks.add(check_id)

    def _renormalise_weights(self) -> None:
        """Adjust scanner weights so enabled categories sum to 1.0."""
        total = sum(s.weight for s in self._org_scanners) + sum(
            s.weight for s in self._repo_scanners
        )
        if total <= 0:
            return
        for org_s in self._org_scanners:
            org_s.weight = org_s.weight / total
        for repo_s in self._repo_scanners:
            repo_s.weight = repo_s.weight / total

    def _filter_results(self, results: list[CheckResult]) -> list[CheckResult]:
        """Remove results for individually disabled checks."""
        if not self._disabled_checks:
            return results
        return [r for r in results if r.check.check_id not in self._disabled_checks]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_org(self, data: OrgAssessmentData) -> list[CheckResult]:
        """Run all org-level scanners against *data*."""
        results: list[CheckResult] = []
        for scanner in self._org_scanners:
            results.extend(scanner.evaluate_org(data))
        return self._filter_results(results)

    def scan_repo(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every repo-level scanner against *data* and return the combined results."""
        results: list[CheckResult] = []
        for scanner in self._repo_scanners:
            results.extend(scanner.evaluate(data))
        return self._filter_results(results)

    @property
    def all_scanners(self) -> list[OrgScanner | Scanner]:
        """Return all scanners (org + repo) for weight/check count queries."""
        return list(self._org_scanners) + list(self._repo_scanners)

    def calculate_category_scores(
        self,
        results: list[CheckResult],
    ) -> dict[Category, CategoryScore]:
        """Group *results* by category and compute per-category scoring data.

        Each check's contribution to the earned score:

        * ``passed``  -> check weight x 1.0
        * ``warning`` -> check weight x 0.5
        * all others  -> 0.0

        The *max_score* for a category is the sum of all check weights within
        that category (``not_applicable`` checks are excluded from max_score
        because they cannot be earned or lost).
        """
        # Build scanner weight lookup keyed on category
        scanner_weights: dict[Category, float] = {}
        for org_s in self._org_scanners:
            scanner_weights[org_s.category] = org_s.weight
        for repo_s in self._repo_scanners:
            scanner_weights[repo_s.category] = repo_s.weight

        # Initialise accumulators for every known category
        scores: dict[Category, float] = {cat: 0.0 for cat in Category}
        max_scores: dict[Category, float] = {cat: 0.0 for cat in Category}
        finding_counts: dict[Category, int] = {cat: 0 for cat in Category}
        pass_counts: dict[Category, int] = {cat: 0 for cat in Category}
        fail_counts: dict[Category, int] = {cat: 0 for cat in Category}

        for result in results:
            cat = result.check.category
            finding_counts[cat] += 1

            if result.status is CheckStatus.not_applicable:
                continue

            max_scores[cat] += result.check.weight
            scores[cat] += result.score

            if result.status is CheckStatus.passed:
                pass_counts[cat] += 1
            elif result.status in (CheckStatus.failed, CheckStatus.error):
                fail_counts[cat] += 1

        category_scores: dict[Category, CategoryScore] = {}
        for cat in Category:
            category_scores[cat] = CategoryScore(
                category=cat,
                score=scores[cat],
                max_score=max_scores[cat],
                weight=scanner_weights.get(cat, 0.0),
                finding_count=finding_counts[cat],
                pass_count=pass_counts[cat],
                fail_count=fail_counts[cat],
            )

        return category_scores

    def calculate_overall_score(
        self,
        category_scores: dict[Category, CategoryScore],
    ) -> float:
        """Compute the overall weighted score on a 0-100 scale.

        Each category contributes ``category_percentage * category_weight`` to
        the final score.  Categories with a zero *max_score* do not contribute
        to either the numerator or the denominator.

        Returns:
            A float in the range [0.0, 100.0], rounded to two decimal places.
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
