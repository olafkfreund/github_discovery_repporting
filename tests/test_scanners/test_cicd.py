from __future__ import annotations

from backend.models.enums import CheckStatus
from backend.scanners.cicd import CICDScanner
from backend.schemas.platform_data import (
    CIWorkflow,
    RepoAssessmentData,
    WorkflowRun,
)
from tests.test_scanners.conftest import _make_failure_run, _make_repo, _make_success_run

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result_map(scanner: CICDScanner, data: RepoAssessmentData) -> dict[str, CheckStatus]:
    """Return a mapping of check_id → CheckStatus for the given data."""
    return {r.check.check_id: r.status for r in scanner.evaluate(data)}


def _repo_with_runs(
    runs: list[WorkflowRun],
    *,
    has_tests: bool = True,
    has_lint: bool = True,
    has_security_scan: bool = True,
    has_deploy: bool = True,
) -> RepoAssessmentData:
    """Return a repo with a single CI workflow loaded with the given *runs*."""
    workflow = CIWorkflow(
        name="CI",
        path=".github/workflows/ci.yml",
        trigger_events=["push", "pull_request"],
        has_tests=has_tests,
        has_lint=has_lint,
        has_security_scan=has_security_scan,
        has_deploy=has_deploy,
        recent_runs=runs,
    )
    return RepoAssessmentData(repo=_make_repo(), ci_workflows=[workflow])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCICDScannerChecks:
    """Unit tests for :class:`CICDScanner`."""

    # ------------------------------------------------------------------
    # Check-count contract
    # ------------------------------------------------------------------

    def test_check_count(self) -> None:
        """CICDScanner must expose exactly 9 checks."""
        scanner = CICDScanner()
        assert len(scanner.checks()) == 9

    def test_check_ids_are_unique(self) -> None:
        """Every check_id in the catalogue must be distinct."""
        scanner = CICDScanner()
        ids = [c.check_id for c in scanner.checks()]
        assert len(ids) == len(set(ids))

    def test_evaluate_returns_one_result_per_check(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """evaluate() must return exactly one CheckResult per ScanCheck."""
        scanner = CICDScanner()
        results = scanner.evaluate(well_protected_repo)
        assert len(results) == len(scanner.checks())

    # ------------------------------------------------------------------
    # CICD-007 always warns
    # ------------------------------------------------------------------

    def test_cicd_007_always_warning(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """CICD-007 must always be a warning because env approvals are not API-inspectable."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, well_protected_repo)
        assert statuses["CICD-007"] is CheckStatus.warning

    # ------------------------------------------------------------------
    # well_protected_repo — repo with CI
    # ------------------------------------------------------------------

    def test_repo_with_ci_passes_cicd_001(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """CICD-001 must pass for a repo that has at least one CI workflow."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, well_protected_repo)
        assert statuses["CICD-001"] is CheckStatus.passed

    def test_repo_with_ci_passes_pr_trigger(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """CICD-002 must pass when a workflow triggers on pull_request events."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, well_protected_repo)
        assert statuses["CICD-002"] is CheckStatus.passed

    def test_repo_with_ci_passes_tests_lint_security_deploy(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """CICD-003 through CICD-006 must pass for a fully-configured CI workflow."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, well_protected_repo)
        for check_id in ("CICD-003", "CICD-004", "CICD-005", "CICD-006"):
            assert statuses[check_id] is CheckStatus.passed, (
                f"{check_id} expected passed but got {statuses[check_id]}"
            )

    # ------------------------------------------------------------------
    # minimal_repo — repo without CI
    # ------------------------------------------------------------------

    def test_repo_without_ci_fails_cicd_001(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """CICD-001 must fail when no CI workflows are defined."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, minimal_repo)
        assert statuses["CICD-001"] is CheckStatus.failed

    def test_repo_without_ci_fails_all_workflow_checks(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """CICD-002 through CICD-006 must fail when there are no workflows."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, minimal_repo)
        for check_id in ("CICD-002", "CICD-003", "CICD-004", "CICD-005", "CICD-006"):
            assert statuses[check_id] is CheckStatus.failed, (
                f"{check_id} expected failed but got {statuses[check_id]}"
            )

    def test_repo_without_ci_cicd_010_not_applicable(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """CICD-010 must be not_applicable when there are no workflow runs."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, minimal_repo)
        assert statuses["CICD-010"] is CheckStatus.not_applicable

    def test_repo_without_ci_cicd_011_not_applicable(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """CICD-011 must be not_applicable when there is no duration data."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, minimal_repo)
        assert statuses["CICD-011"] is CheckStatus.not_applicable

    # ------------------------------------------------------------------
    # CICD-010 — pipeline success rate
    # ------------------------------------------------------------------

    def test_pipeline_success_rate_high_passes_cicd_010(self) -> None:
        """CICD-010 must pass when all 20 recent runs succeeded (100 %)."""
        runs = [_make_success_run() for _ in range(20)]
        data = _repo_with_runs(runs)
        scanner = CICDScanner()
        statuses = _result_map(scanner, data)
        assert statuses["CICD-010"] is CheckStatus.passed

    def test_pipeline_success_rate_exactly_95_passes_cicd_010(self) -> None:
        """CICD-010 must pass at exactly the 95 % threshold (19/20 successes)."""
        runs = [_make_success_run() for _ in range(19)] + [_make_failure_run()]
        data = _repo_with_runs(runs)
        scanner = CICDScanner()
        statuses = _result_map(scanner, data)
        assert statuses["CICD-010"] is CheckStatus.passed

    def test_pipeline_success_rate_low_fails_cicd_010(self) -> None:
        """CICD-010 must fail when fewer than 80 % of runs succeeded."""
        # 5 successes out of 20 = 25 %
        runs = [_make_success_run() for _ in range(5)] + [_make_failure_run() for _ in range(15)]
        data = _repo_with_runs(runs)
        scanner = CICDScanner()
        statuses = _result_map(scanner, data)
        assert statuses["CICD-010"] is CheckStatus.failed

    def test_pipeline_success_rate_between_80_and_95_warns_cicd_010(self) -> None:
        """CICD-010 must warn when the success rate is between 80 % and 95 %."""
        # 17 successes out of 20 = 85 %
        runs = [_make_success_run() for _ in range(17)] + [_make_failure_run() for _ in range(3)]
        data = _repo_with_runs(runs)
        scanner = CICDScanner()
        statuses = _result_map(scanner, data)
        assert statuses["CICD-010"] is CheckStatus.warning

    def test_pipeline_success_rate_evidence_populated(self) -> None:
        """The CICD-010 result evidence must expose total, success, and rate."""
        runs = [_make_success_run() for _ in range(20)]
        data = _repo_with_runs(runs)
        scanner = CICDScanner()
        results = {r.check.check_id: r for r in scanner.evaluate(data)}
        cicd010 = results["CICD-010"]
        assert cicd010.evidence is not None
        assert cicd010.evidence["total_runs"] == 20
        assert cicd010.evidence["success_runs"] == 20
        assert cicd010.evidence["success_rate_pct"] == 100.0

    # ------------------------------------------------------------------
    # CICD-010 — no completed runs → not_applicable
    # ------------------------------------------------------------------

    def test_no_completed_runs_cicd_010_not_applicable(self) -> None:
        """CICD-010 must be not_applicable when all runs lack a conclusion."""
        in_progress_run = WorkflowRun(
            status="in_progress",
            conclusion=None,
            duration_seconds=None,
        )
        workflow = CIWorkflow(
            name="CI",
            path=".github/workflows/ci.yml",
            trigger_events=["pull_request"],
            has_tests=True,
            recent_runs=[in_progress_run],
        )
        data = RepoAssessmentData(repo=_make_repo(), ci_workflows=[workflow])
        scanner = CICDScanner()
        statuses = _result_map(scanner, data)
        assert statuses["CICD-010"] is CheckStatus.not_applicable

    # ------------------------------------------------------------------
    # CICD-011 — average build time
    # ------------------------------------------------------------------

    def test_fast_builds_pass_cicd_011(self) -> None:
        """CICD-011 must pass when the average build duration is under 10 minutes."""
        runs = [_make_success_run(duration_seconds=300) for _ in range(5)]
        data = _repo_with_runs(runs)
        scanner = CICDScanner()
        statuses = _result_map(scanner, data)
        assert statuses["CICD-011"] is CheckStatus.passed

    def test_slow_builds_fail_cicd_011(self) -> None:
        """CICD-011 must fail when the average build duration exceeds 10 minutes."""
        slow_run = WorkflowRun(
            status="completed",
            conclusion="success",
            duration_seconds=750,  # 12.5 minutes
        )
        workflow = CIWorkflow(
            name="CI",
            path=".github/workflows/ci.yml",
            trigger_events=["pull_request"],
            has_tests=True,
            recent_runs=[slow_run],
        )
        data = RepoAssessmentData(repo=_make_repo(), ci_workflows=[workflow])
        scanner = CICDScanner()
        statuses = _result_map(scanner, data)
        assert statuses["CICD-011"] is CheckStatus.failed

    # ------------------------------------------------------------------
    # Partial repo — tests only, no lint/security/deploy
    # ------------------------------------------------------------------

    def test_partial_repo_tests_pass_cicd_003(
        self, partial_repo: RepoAssessmentData
    ) -> None:
        """CICD-003 must pass when at least one workflow has has_tests=True."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, partial_repo)
        assert statuses["CICD-003"] is CheckStatus.passed

    def test_partial_repo_no_lint_fails_cicd_004(
        self, partial_repo: RepoAssessmentData
    ) -> None:
        """CICD-004 must fail when no workflow has has_lint=True."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, partial_repo)
        assert statuses["CICD-004"] is CheckStatus.failed

    def test_partial_repo_no_security_scan_fails_cicd_005(
        self, partial_repo: RepoAssessmentData
    ) -> None:
        """CICD-005 must fail when no workflow has has_security_scan=True."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, partial_repo)
        assert statuses["CICD-005"] is CheckStatus.failed

    def test_partial_repo_no_deploy_fails_cicd_006(
        self, partial_repo: RepoAssessmentData
    ) -> None:
        """CICD-006 must fail when no workflow has has_deploy=True."""
        scanner = CICDScanner()
        statuses = _result_map(scanner, partial_repo)
        assert statuses["CICD-006"] is CheckStatus.failed
