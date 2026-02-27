from __future__ import annotations

from dataclasses import dataclass

from backend.models.enums import Category
from backend.scanners.base import CheckResult, Scanner
from backend.scanners.cicd import CICDScanner
from backend.scanners.code_quality import CodeQualityScanner
from backend.scanners.collaboration import CollaborationScanner
from backend.scanners.governance import GovernanceScanner
from backend.scanners.security import SecurityScanner
from backend.schemas.platform_data import RepoAssessmentData


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
        """Percentage score for this category (0–100).

        Returns 0.0 when *max_score* is zero to avoid division by zero.
        """
        if self.max_score == 0.0:
            return 0.0
        return (self.score / self.max_score) * 100.0


class ScanOrchestrator:
    """Coordinates all scanner instances and produces a unified assessment.

    Usage::

        orchestrator = ScanOrchestrator()
        results = orchestrator.scan_repo(data)
        category_scores = orchestrator.calculate_category_scores(results)
        overall = orchestrator.calculate_overall_score(category_scores)
    """

    def __init__(self) -> None:
        self._scanners: list[Scanner] = [
            SecurityScanner(),
            CICDScanner(),
            CodeQualityScanner(),
            CollaborationScanner(),
            GovernanceScanner(),
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_repo(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every scanner against *data* and return the combined results.

        The order of results mirrors the order of scanners: security first,
        then cicd, code_quality, collaboration, governance.
        """
        results: list[CheckResult] = []
        for scanner in self._scanners:
            results.extend(scanner.evaluate(data))
        return results

    def calculate_category_scores(
        self,
        results: list[CheckResult],
    ) -> dict[Category, CategoryScore]:
        """Group *results* by category and compute per-category scoring data.

        Each check's contribution to the earned score:

        * ``passed``  → check weight × 1.0
        * ``warning`` → check weight × 0.5
        * all others  → 0.0

        The *max_score* for a category is the sum of all check weights within
        that category (``not_applicable`` checks are excluded from max_score
        because they cannot be earned or lost).
        """
        from backend.models.enums import CheckStatus  # local import avoids circular risk

        # Build scanner weight lookup keyed on category
        scanner_weights: dict[Category, float] = {
            s.category: s.weight for s in self._scanners
        }

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
                # Skip — neither earned nor possible
                continue

            # Add to max_score for all applicable checks
            acc["max_score"] += result.check.weight

            # Earned score (already computed by CheckResult.__post_init__)
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
        """Compute the overall weighted score on a 0–100 scale.

        Each category contributes ``category_percentage * category_weight`` to
        the final score.  Categories with a zero *max_score* (i.e. every check
        was ``not_applicable``) do not contribute to either the numerator or the
        denominator so they cannot artificially deflate the overall result.

        Returns:
            A float in the range [0.0, 100.0], rounded to two decimal places.
        """
        weighted_sum: float = 0.0
        total_weight: float = 0.0

        for cat_score in category_scores.values():
            if cat_score.max_score == 0.0:
                # Entirely not_applicable category — exclude from weighting
                continue
            weighted_sum += cat_score.percentage * cat_score.weight
            total_weight += cat_score.weight

        if total_weight == 0.0:
            return 0.0

        return round(weighted_sum / total_weight, 2)
