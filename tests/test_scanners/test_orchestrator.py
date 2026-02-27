from __future__ import annotations

from backend.models.enums import Category
from backend.scanners.orchestrator import CategoryScore, ScanOrchestrator
from backend.schemas.platform_data import OrgAssessmentData, RepoAssessmentData

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expected_repo_check_count() -> int:
    """Return the total number of checks across all 14 repo-level scanners."""
    orchestrator = ScanOrchestrator()
    return sum(len(s.checks()) for s in orchestrator._repo_scanners)


def _expected_org_check_count() -> int:
    """Return the total number of checks across all 2 org-level scanners."""
    orchestrator = ScanOrchestrator()
    return sum(len(s.checks()) for s in orchestrator._org_scanners)


def _expected_total_check_count() -> int:
    """Return total checks across all 16 scanners."""
    return _expected_repo_check_count() + _expected_org_check_count()


def _score_repo(data: RepoAssessmentData) -> tuple[list, dict[Category, CategoryScore], float]:
    """Run the repo-level orchestration pipeline and return (results, category_scores, overall)."""
    orchestrator = ScanOrchestrator()
    results = orchestrator.scan_repo(data)
    category_scores = orchestrator.calculate_category_scores(results)
    overall = orchestrator.calculate_overall_score(category_scores)
    return results, category_scores, overall


def _score_full(
    org_data: OrgAssessmentData,
    repo_data: RepoAssessmentData,
) -> tuple[list, dict[Category, CategoryScore], float]:
    """Run full org + repo scan and return combined results."""
    orchestrator = ScanOrchestrator()
    org_results = orchestrator.scan_org(org_data)
    repo_results = orchestrator.scan_repo(repo_data)
    all_results = org_results + repo_results
    category_scores = orchestrator.calculate_category_scores(all_results)
    overall = orchestrator.calculate_overall_score(category_scores)
    return all_results, category_scores, overall


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScanOrchestrator:
    """Integration tests for :class:`ScanOrchestrator`."""

    # ------------------------------------------------------------------
    # Result count contract
    # ------------------------------------------------------------------

    def test_scan_repo_returns_all_results(self, well_protected_repo: RepoAssessmentData) -> None:
        """scan_repo() must return one CheckResult per check across all repo scanners."""
        expected = _expected_repo_check_count()
        orchestrator = ScanOrchestrator()
        results = orchestrator.scan_repo(well_protected_repo)
        assert len(results) == expected

    def test_scan_repo_result_count_matches_scanner_sum(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """Result count must equal the sum of individual repo scanner check counts."""
        expected = _expected_repo_check_count()
        orchestrator = ScanOrchestrator()
        results = orchestrator.scan_repo(minimal_repo)
        assert len(results) == expected

    def test_scan_org_returns_all_results(self, well_configured_org: OrgAssessmentData) -> None:
        """scan_org() must return one CheckResult per check across all org scanners."""
        expected = _expected_org_check_count()
        orchestrator = ScanOrchestrator()
        results = orchestrator.scan_org(well_configured_org)
        assert len(results) == expected

    def test_total_check_count_is_correct(self) -> None:
        """The combined check catalogue across all 16 scanners should be substantial."""
        total = _expected_total_check_count()
        # 16 scanners with varying check counts should total > 150
        assert total > 150, f"Expected > 150 total checks, got {total}"

    def test_org_scanner_count_is_23(self) -> None:
        """The 2 org-level scanners must total 23 checks (11 + 12)."""
        assert _expected_org_check_count() == 23

    # ------------------------------------------------------------------
    # Category scores -- structural guarantees
    # ------------------------------------------------------------------

    def test_category_scores_have_all_categories(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """calculate_category_scores() must return an entry for every Category member."""
        _, category_scores, _ = _score_repo(well_protected_repo)
        for cat in Category:
            assert cat in category_scores, f"Category {cat} missing from category_scores"

    def test_category_scores_all_sixteen_categories_present(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """All 16 categories must appear even when most checks are not_applicable."""
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

    # ------------------------------------------------------------------
    # Overall score bounds
    # ------------------------------------------------------------------

    def test_overall_score_range_well_protected(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """Overall score must be in [0.0, 100.0] for a well-protected repo."""
        _, _, overall = _score_repo(well_protected_repo)
        assert 0.0 <= overall <= 100.0

    def test_overall_score_range_minimal(self, minimal_repo: RepoAssessmentData) -> None:
        """Overall score must be in [0.0, 100.0] for a minimal repo."""
        _, _, overall = _score_repo(minimal_repo)
        assert 0.0 <= overall <= 100.0

    def test_overall_score_range_partial(self, partial_repo: RepoAssessmentData) -> None:
        """Overall score must be in [0.0, 100.0] for a partially-configured repo."""
        _, _, overall = _score_repo(partial_repo)
        assert 0.0 <= overall <= 100.0

    # ------------------------------------------------------------------
    # Score ordering: well_protected > partial > minimal
    # ------------------------------------------------------------------

    def test_well_protected_score_high(self, well_protected_repo: RepoAssessmentData) -> None:
        """A fully hardened repo should score above 60 overall."""
        _, _, overall = _score_repo(well_protected_repo)
        assert overall > 60.0, f"Expected overall > 60, got {overall}"

    def test_minimal_repo_score_low(self, minimal_repo: RepoAssessmentData) -> None:
        """A repo with nothing configured should score below 40 overall."""
        _, _, overall = _score_repo(minimal_repo)
        assert overall < 40.0, f"Expected overall < 40, got {overall}"

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

    def test_category_weights_sum_to_one(self) -> None:
        """The 16 scanner category weights must sum to 1.0."""
        orchestrator = ScanOrchestrator()
        weights = [s.weight for s in orchestrator.all_scanners]
        total = sum(weights)
        assert abs(total - 1.0) < 1e-9, f"Category weights sum to {total}, expected 1.0"

    # ------------------------------------------------------------------
    # Org + repo combined scanning
    # ------------------------------------------------------------------

    def test_full_scan_includes_org_and_repo_results(
        self,
        well_configured_org: OrgAssessmentData,
        well_protected_repo: RepoAssessmentData,
    ) -> None:
        """A full scan must produce results from both org and repo scanners."""
        all_results, _, _ = _score_full(well_configured_org, well_protected_repo)
        expected = _expected_org_check_count() + _expected_repo_check_count()
        assert len(all_results) == expected

    def test_full_scan_org_categories_have_findings(
        self,
        well_configured_org: OrgAssessmentData,
        well_protected_repo: RepoAssessmentData,
    ) -> None:
        """Org-level categories must have findings after a full scan."""
        _, category_scores, _ = _score_full(well_configured_org, well_protected_repo)
        assert category_scores[Category.platform_arch].finding_count > 0
        assert category_scores[Category.identity_access].finding_count > 0

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_scan_is_deterministic(self, well_protected_repo: RepoAssessmentData) -> None:
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
            category=Category.platform_arch,
            score=0.0,
            max_score=0.0,
            weight=0.06,
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
            weight=0.10,
            finding_count=5,
            pass_count=5,
            fail_count=0,
        )
        assert cs.percentage == 100.0
