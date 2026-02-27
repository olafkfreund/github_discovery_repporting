from __future__ import annotations

from backend.models.enums import Category
from backend.scanners.cicd import CICDScanner
from backend.scanners.code_quality import CodeQualityScanner
from backend.scanners.collaboration import CollaborationScanner
from backend.scanners.governance import GovernanceScanner
from backend.scanners.orchestrator import CategoryScore, ScanOrchestrator
from backend.scanners.security import SecurityScanner
from backend.schemas.platform_data import RepoAssessmentData

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expected_check_count() -> int:
    """Return the total number of checks across all five scanners.

    SecurityScanner: 15
    CICDScanner:      9
    CodeQualityScanner: 5
    CollaborationScanner: 5
    GovernanceScanner:    5
    Total:            39
    """
    return (
        len(SecurityScanner().checks())
        + len(CICDScanner().checks())
        + len(CodeQualityScanner().checks())
        + len(CollaborationScanner().checks())
        + len(GovernanceScanner().checks())
    )


def _score_repo(data: RepoAssessmentData) -> tuple[list, dict[Category, CategoryScore], float]:
    """Run the full orchestration pipeline and return (results, category_scores, overall)."""
    orchestrator = ScanOrchestrator()
    results = orchestrator.scan_repo(data)
    category_scores = orchestrator.calculate_category_scores(results)
    overall = orchestrator.calculate_overall_score(category_scores)
    return results, category_scores, overall


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScanOrchestrator:
    """Integration tests for :class:`ScanOrchestrator`."""

    # ------------------------------------------------------------------
    # Result count contract
    # ------------------------------------------------------------------

    def test_scan_repo_returns_all_results(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """scan_repo() must return one CheckResult per check across all scanners."""
        expected = _expected_check_count()
        orchestrator = ScanOrchestrator()
        results = orchestrator.scan_repo(well_protected_repo)
        assert len(results) == expected

    def test_scan_repo_result_count_matches_scanner_sum(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """Result count must equal the sum of individual scanner check counts."""
        expected = _expected_check_count()
        orchestrator = ScanOrchestrator()
        results = orchestrator.scan_repo(minimal_repo)
        assert len(results) == expected

    def test_check_count_is_39(self) -> None:
        """The combined check catalogue across all scanners must total 39."""
        assert _expected_check_count() == 39

    # ------------------------------------------------------------------
    # Category scores — structural guarantees
    # ------------------------------------------------------------------

    def test_category_scores_have_all_categories(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """calculate_category_scores() must return an entry for every Category member."""
        _, category_scores, _ = _score_repo(well_protected_repo)
        for cat in Category:
            assert cat in category_scores, f"Category {cat} missing from category_scores"

    def test_category_scores_all_five_categories_present_for_minimal_repo(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """All five categories must appear even when most checks are not_applicable."""
        _, category_scores, _ = _score_repo(minimal_repo)
        assert len(category_scores) == len(list(Category))

    def test_category_score_percentage_in_range(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """Every CategoryScore.percentage must be in [0.0, 100.0]."""
        _, category_scores, _ = _score_repo(well_protected_repo)
        for cat, cs in category_scores.items():
            assert 0.0 <= cs.percentage <= 100.0, (
                f"Category {cat} percentage {cs.percentage} is out of range"
            )

    def test_category_score_finding_count_matches_scanner(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """Each category's finding_count must match its scanner's check count."""
        scanner_counts = {
            Category.security: len(SecurityScanner().checks()),
            Category.cicd: len(CICDScanner().checks()),
            Category.code_quality: len(CodeQualityScanner().checks()),
            Category.collaboration: len(CollaborationScanner().checks()),
            Category.governance: len(GovernanceScanner().checks()),
        }
        _, category_scores, _ = _score_repo(well_protected_repo)
        for cat, expected_count in scanner_counts.items():
            actual = category_scores[cat].finding_count
            assert actual == expected_count, (
                f"Category {cat}: expected finding_count={expected_count}, got {actual}"
            )

    # ------------------------------------------------------------------
    # Overall score bounds
    # ------------------------------------------------------------------

    def test_overall_score_range_well_protected(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """Overall score must be in [0.0, 100.0] for a well-protected repo."""
        _, _, overall = _score_repo(well_protected_repo)
        assert 0.0 <= overall <= 100.0

    def test_overall_score_range_minimal(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """Overall score must be in [0.0, 100.0] for a minimal repo."""
        _, _, overall = _score_repo(minimal_repo)
        assert 0.0 <= overall <= 100.0

    def test_overall_score_range_partial(
        self, partial_repo: RepoAssessmentData
    ) -> None:
        """Overall score must be in [0.0, 100.0] for a partially-configured repo."""
        _, _, overall = _score_repo(partial_repo)
        assert 0.0 <= overall <= 100.0

    # ------------------------------------------------------------------
    # Score ordering: well_protected > partial > minimal
    # ------------------------------------------------------------------

    def test_well_protected_score_high(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """A fully hardened repo should score above 70 overall."""
        _, _, overall = _score_repo(well_protected_repo)
        assert overall > 70.0, f"Expected overall > 70, got {overall}"

    def test_minimal_repo_score_low(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """A repo with nothing configured should score below 30 overall."""
        _, _, overall = _score_repo(minimal_repo)
        assert overall < 30.0, f"Expected overall < 30, got {overall}"

    def test_partial_repo_score_between_minimal_and_well_protected(
        self,
        minimal_repo: RepoAssessmentData,
        partial_repo: RepoAssessmentData,
        well_protected_repo: RepoAssessmentData,
    ) -> None:
        """The partial repo score must sit between the minimal and well-protected scores."""
        _, _, minimal_score = _score_repo(minimal_repo)
        _, _, partial_score = _score_repo(partial_repo)
        _, _, well_score = _score_repo(well_protected_repo)
        assert minimal_score < partial_score < well_score, (
            f"Expected {minimal_score:.2f} < {partial_score:.2f} < {well_score:.2f}"
        )

    # ------------------------------------------------------------------
    # Category weight validation
    # ------------------------------------------------------------------

    def test_category_weights_sum_to_one(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """The five scanner category weights must sum to 1.0."""
        _, category_scores, _ = _score_repo(well_protected_repo)
        active_weights = [
            cs.weight
            for cs in category_scores.values()
            if cs.weight > 0.0
        ]
        total = sum(active_weights)
        assert abs(total - 1.0) < 1e-9, f"Category weights sum to {total}, expected 1.0"

    # ------------------------------------------------------------------
    # Pass / fail count consistency
    # ------------------------------------------------------------------

    def test_well_protected_security_category_high_pass_count(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """Security pass_count must be >= 13 for a well-protected repo.

        SEC-022 is always a warning, so at most 14 of 15 checks can pass.
        The two governance checks that are always warnings reduce possible
        passes, but the security category alone should have >=13 passes
        (all 14 non-SEC-022 checks pass).
        """
        _, category_scores, _ = _score_repo(well_protected_repo)
        sec_score = category_scores[Category.security]
        assert sec_score.pass_count >= 13

    def test_minimal_repo_security_category_zero_passes(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """Security pass_count must be 0 for a repo with no security configuration."""
        _, category_scores, _ = _score_repo(minimal_repo)
        sec_score = category_scores[Category.security]
        assert sec_score.pass_count == 0

    # ------------------------------------------------------------------
    # Determinism — running the same data twice yields identical scores
    # ------------------------------------------------------------------

    def test_scan_is_deterministic(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """Scanning the same data twice must produce identical overall scores."""
        orchestrator = ScanOrchestrator()
        results_a = orchestrator.scan_repo(well_protected_repo)
        cat_a = orchestrator.calculate_category_scores(results_a)
        score_a = orchestrator.calculate_overall_score(cat_a)

        results_b = orchestrator.scan_repo(well_protected_repo)
        cat_b = orchestrator.calculate_category_scores(results_b)
        score_b = orchestrator.calculate_overall_score(cat_b)

        assert score_a == score_b

    # ------------------------------------------------------------------
    # CategoryScore.percentage property edge cases
    # ------------------------------------------------------------------

    def test_category_score_percentage_zero_when_max_score_is_zero(self) -> None:
        """CategoryScore.percentage must return 0.0 when max_score is zero."""
        cs = CategoryScore(
            category=Category.security,
            score=0.0,
            max_score=0.0,
            weight=0.40,
            finding_count=0,
            pass_count=0,
            fail_count=0,
        )
        assert cs.percentage == 0.0

    def test_category_score_percentage_100_when_fully_passed(self) -> None:
        """CategoryScore.percentage must be 100.0 when score equals max_score."""
        cs = CategoryScore(
            category=Category.cicd,
            score=10.0,
            max_score=10.0,
            weight=0.20,
            finding_count=5,
            pass_count=5,
            fail_count=0,
        )
        assert cs.percentage == 100.0
