from __future__ import annotations

from dataclasses import dataclass

from backend.models.enums import Category
from backend.scanners.base import CheckResult, OrgScanner, Scanner
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


class ScanOrchestrator:
    """Coordinates all 16 scanner instances and produces a unified assessment.

    Usage::

        orchestrator = ScanOrchestrator()

        # Org-level scanning
        org_results = orchestrator.scan_org(org_data)

        # Repo-level scanning
        repo_results = orchestrator.scan_repo(repo_data)

        # Combine and score
        all_results = org_results + repo_results
        category_scores = orchestrator.calculate_category_scores(all_results)
        overall = orchestrator.calculate_overall_score(category_scores)
    """

    def __init__(self) -> None:
        # Org-level scanners (implement evaluate_org)
        self._org_scanners: list[OrgScanner] = [
            PlatformArchScanner(),
            IdentityAccessScanner(),
        ]

        # Repo-level scanners (implement evaluate)
        self._repo_scanners: list[Scanner] = [
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_org(self, data: OrgAssessmentData) -> list[CheckResult]:
        """Run all org-level scanners against *data*."""
        results: list[CheckResult] = []
        for scanner in self._org_scanners:
            results.extend(scanner.evaluate_org(data))
        return results

    def scan_repo(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every repo-level scanner against *data* and return the combined results."""
        results: list[CheckResult] = []
        for scanner in self._repo_scanners:
            results.extend(scanner.evaluate(data))
        return results

    @property
    def all_scanners(self) -> list:
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
        from backend.models.enums import CheckStatus

        # Build scanner weight lookup keyed on category
        scanner_weights: dict[Category, float] = {}
        for s in self._org_scanners:
            scanner_weights[s.category] = s.weight
        for s in self._repo_scanners:
            scanner_weights[s.category] = s.weight

        # Initialise accumulators for every known category
        accumulators: dict[Category, dict] = {
            cat: {
                "score": 0.0,
                "max_score": 0.0,
                "finding_count": 0,
                "pass_count": 0,
                "fail_count": 0,
            }
            for cat in Category
        }

        for result in results:
            cat = result.check.category
            acc = accumulators[cat]
            acc["finding_count"] += 1

            if result.status is CheckStatus.not_applicable:
                continue

            acc["max_score"] += result.check.weight
            acc["score"] += result.score

            if result.status is CheckStatus.passed:
                acc["pass_count"] += 1
            elif result.status in (CheckStatus.failed, CheckStatus.error):
                acc["fail_count"] += 1

        category_scores: dict[Category, CategoryScore] = {}
        for cat, acc in accumulators.items():
            category_scores[cat] = CategoryScore(
                category=cat,
                score=acc["score"],
                max_score=acc["max_score"],
                weight=scanner_weights.get(cat, 0.0),
                finding_count=acc["finding_count"],
                pass_count=acc["pass_count"],
                fail_count=acc["fail_count"],
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
