from __future__ import annotations

from backend.models.enums import CheckStatus
from backend.scanners.security import SecurityScanner
from backend.schemas.platform_data import (
    BranchProtection,
    RepoAssessmentData,
    SecurityFeatures,
    VulnerabilityAlert,
)
from tests.test_scanners.conftest import _make_repo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result_map(scanner: SecurityScanner, data: RepoAssessmentData) -> dict[str, CheckStatus]:
    """Return a mapping of check_id → CheckStatus for the given data."""
    return {r.check.check_id: r.status for r in scanner.evaluate(data)}


def _no_protection_repo() -> RepoAssessmentData:
    """Return a repo with an explicit *unprotected* BranchProtection object."""
    bp = BranchProtection(
        is_protected=False,
        required_reviews=0,
        dismiss_stale_reviews=False,
        require_code_owner_reviews=False,
        enforce_admins=False,
        allow_force_pushes=True,
        require_signed_commits=False,
    )
    return RepoAssessmentData(
        repo=_make_repo(),
        branch_protection=bp,
        security=SecurityFeatures(
            dependabot_enabled=False,
            secret_scanning_enabled=False,
            vulnerability_alerts=[],
            has_security_policy=False,
        ),
    )


def _repo_with_critical_vulns() -> RepoAssessmentData:
    """Return a repo that carries two open critical-severity vulnerability alerts."""
    security = SecurityFeatures(
        dependabot_enabled=True,
        secret_scanning_enabled=True,
        vulnerability_alerts=[
            VulnerabilityAlert(
                severity="critical",
                package="requests",
                title="Remote code execution in requests",
                state="open",
            ),
            VulnerabilityAlert(
                severity="critical",
                package="urllib3",
                title="Heap overflow in urllib3",
                state="open",
            ),
        ],
        has_security_policy=True,
    )
    bp = BranchProtection(
        is_protected=True,
        required_reviews=2,
        dismiss_stale_reviews=True,
        require_code_owner_reviews=True,
        enforce_admins=True,
        allow_force_pushes=False,
        require_signed_commits=True,
    )
    return RepoAssessmentData(
        repo=_make_repo(),
        branch_protection=bp,
        security=security,
        has_sbom=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSecurityScannerChecks:
    """Unit tests for :class:`SecurityScanner`."""

    # ------------------------------------------------------------------
    # Check-count contract
    # ------------------------------------------------------------------

    def test_check_count(self) -> None:
        """SecurityScanner must expose exactly 15 checks."""
        scanner = SecurityScanner()
        assert len(scanner.checks()) == 15

    def test_check_ids_are_unique(self) -> None:
        """Every check_id in the catalogue must be distinct."""
        scanner = SecurityScanner()
        ids = [c.check_id for c in scanner.checks()]
        assert len(ids) == len(set(ids))

    def test_evaluate_returns_one_result_per_check(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """evaluate() must return exactly one CheckResult per ScanCheck."""
        scanner = SecurityScanner()
        results = scanner.evaluate(well_protected_repo)
        assert len(results) == len(scanner.checks())

    # ------------------------------------------------------------------
    # well_protected_repo — all checks should pass (SEC-022 always warns)
    # ------------------------------------------------------------------

    def test_well_protected_repo_all_pass(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """All security checks must pass for a fully-hardened repository.

        SEC-022 is permanently set to ``warning`` because CI-action pinning
        cannot be verified programmatically, so it is excluded from the
        all-pass assertion.
        """
        scanner = SecurityScanner()
        statuses = _result_map(scanner, well_protected_repo)

        non_warning_ids = [cid for cid in statuses if cid != "SEC-022"]
        for check_id in non_warning_ids:
            assert statuses[check_id] is CheckStatus.passed, (
                f"{check_id} expected passed but got {statuses[check_id]}"
            )

    def test_sec_022_always_warning(
        self, well_protected_repo: RepoAssessmentData
    ) -> None:
        """SEC-022 must always be a warning regardless of repo configuration."""
        scanner = SecurityScanner()
        statuses = _result_map(scanner, well_protected_repo)
        assert statuses["SEC-022"] is CheckStatus.warning

    # ------------------------------------------------------------------
    # minimal_repo — checks that require security data → not_applicable
    # ------------------------------------------------------------------

    def test_minimal_repo_branch_checks_fail(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """Branch protection checks must fail when no branch protection exists."""
        scanner = SecurityScanner()
        statuses = _result_map(scanner, minimal_repo)
        branch_check_ids = ["SEC-001", "SEC-002", "SEC-003", "SEC-004", "SEC-005", "SEC-006", "SEC-007"]
        for check_id in branch_check_ids:
            assert statuses[check_id] is CheckStatus.failed, (
                f"{check_id} expected failed but got {statuses[check_id]}"
            )

    def test_minimal_repo_security_checks_not_applicable(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """Vulnerability/dependency checks must be not_applicable with no SecurityFeatures."""
        scanner = SecurityScanner()
        statuses = _result_map(scanner, minimal_repo)
        not_applicable_ids = ["SEC-010", "SEC-011", "SEC-012", "SEC-013", "SEC-014", "SEC-021"]
        for check_id in not_applicable_ids:
            assert statuses[check_id] is CheckStatus.not_applicable, (
                f"{check_id} expected not_applicable but got {statuses[check_id]}"
            )

    def test_minimal_repo_sbom_fails(
        self, minimal_repo: RepoAssessmentData
    ) -> None:
        """SEC-020 must fail when has_sbom is False."""
        scanner = SecurityScanner()
        statuses = _result_map(scanner, minimal_repo)
        assert statuses["SEC-020"] is CheckStatus.failed

    # ------------------------------------------------------------------
    # No branch protection object → all branch checks fail
    # ------------------------------------------------------------------

    def test_no_branch_protection_fails_branch_checks(self) -> None:
        """All SEC-001 through SEC-007 must fail when branch_protection is None."""
        data = RepoAssessmentData(repo=_make_repo())
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)

        for check_id in ("SEC-001", "SEC-002", "SEC-003", "SEC-004", "SEC-005", "SEC-006", "SEC-007"):
            assert statuses[check_id] is CheckStatus.failed, (
                f"{check_id} expected failed but got {statuses[check_id]}"
            )

    def test_explicit_unprotected_branch_fails_sec_001(self) -> None:
        """SEC-001 must fail when BranchProtection.is_protected is explicitly False."""
        data = _no_protection_repo()
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)
        assert statuses["SEC-001"] is CheckStatus.failed

    # ------------------------------------------------------------------
    # Critical vulnerability check
    # ------------------------------------------------------------------

    def test_critical_vulns_fail_sec_011(self) -> None:
        """SEC-011 must fail when open critical-severity vulnerability alerts exist."""
        data = _repo_with_critical_vulns()
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)
        assert statuses["SEC-011"] is CheckStatus.failed

    def test_critical_vulns_evidence_contains_count(self) -> None:
        """The SEC-011 result evidence must expose the alert count and package names."""
        data = _repo_with_critical_vulns()
        scanner = SecurityScanner()
        results = {r.check.check_id: r for r in scanner.evaluate(data)}
        sec011 = results["SEC-011"]
        assert sec011.evidence is not None
        assert sec011.evidence["critical_alert_count"] == 2
        assert "requests" in sec011.evidence["packages"]
        assert "urllib3" in sec011.evidence["packages"]

    def test_no_vulns_passes_sec_011_and_sec_012(self) -> None:
        """Both SEC-011 and SEC-012 must pass when vulnerability_alerts is empty."""
        security = SecurityFeatures(
            dependabot_enabled=True,
            secret_scanning_enabled=True,
            vulnerability_alerts=[],
            has_security_policy=True,
        )
        data = RepoAssessmentData(
            repo=_make_repo(),
            security=security,
        )
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)
        assert statuses["SEC-011"] is CheckStatus.passed
        assert statuses["SEC-012"] is CheckStatus.passed

    def test_high_vuln_only_fails_sec_012_not_sec_011(self) -> None:
        """SEC-011 must pass and SEC-012 must fail when only high-severity alerts exist."""
        security = SecurityFeatures(
            dependabot_enabled=True,
            secret_scanning_enabled=True,
            vulnerability_alerts=[
                VulnerabilityAlert(
                    severity="high",
                    package="django",
                    title="SQL injection in Django ORM",
                    state="open",
                ),
            ],
            has_security_policy=True,
        )
        data = RepoAssessmentData(repo=_make_repo(), security=security)
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)
        assert statuses["SEC-011"] is CheckStatus.passed
        assert statuses["SEC-012"] is CheckStatus.failed

    # ------------------------------------------------------------------
    # Supply-chain / policy checks
    # ------------------------------------------------------------------

    def test_sbom_present_passes_sec_020(self) -> None:
        """SEC-020 must pass when has_sbom is True."""
        data = RepoAssessmentData(repo=_make_repo(), has_sbom=True)
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)
        assert statuses["SEC-020"] is CheckStatus.passed

    def test_security_policy_present_passes_sec_021(self) -> None:
        """SEC-021 must pass when SecurityFeatures.has_security_policy is True."""
        security = SecurityFeatures(
            dependabot_enabled=False,
            secret_scanning_enabled=False,
            vulnerability_alerts=[],
            has_security_policy=True,
        )
        data = RepoAssessmentData(repo=_make_repo(), security=security)
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)
        assert statuses["SEC-021"] is CheckStatus.passed

    def test_missing_security_policy_fails_sec_021(self) -> None:
        """SEC-021 must fail when SecurityFeatures.has_security_policy is False."""
        security = SecurityFeatures(
            dependabot_enabled=True,
            secret_scanning_enabled=True,
            vulnerability_alerts=[],
            has_security_policy=False,
        )
        data = RepoAssessmentData(repo=_make_repo(), security=security)
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)
        assert statuses["SEC-021"] is CheckStatus.failed

    # ------------------------------------------------------------------
    # Signed-commits check
    # ------------------------------------------------------------------

    def test_signed_commits_passes_sec_007(self) -> None:
        """SEC-007 must pass when require_signed_commits is True."""
        bp = BranchProtection(
            is_protected=True,
            required_reviews=2,
            dismiss_stale_reviews=True,
            require_code_owner_reviews=True,
            enforce_admins=True,
            allow_force_pushes=False,
            require_signed_commits=True,
        )
        data = RepoAssessmentData(repo=_make_repo(), branch_protection=bp)
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)
        assert statuses["SEC-007"] is CheckStatus.passed

    def test_unsigned_commits_fails_sec_007(self) -> None:
        """SEC-007 must fail when require_signed_commits is False."""
        bp = BranchProtection(
            is_protected=True,
            required_reviews=2,
            dismiss_stale_reviews=True,
            require_code_owner_reviews=True,
            enforce_admins=True,
            allow_force_pushes=False,
            require_signed_commits=False,
        )
        data = RepoAssessmentData(repo=_make_repo(), branch_protection=bp)
        scanner = SecurityScanner()
        statuses = _result_map(scanner, data)
        assert statuses["SEC-007"] is CheckStatus.failed
