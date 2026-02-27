from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import BranchProtection, RepoAssessmentData, SecurityFeatures


class SecurityScanner:
    """Evaluates repository security posture across branch protection,
    vulnerability management, and supply-chain controls.

    Category weight: 0.40 (the heaviest of all scanners).
    """

    category: Category = Category.security
    weight: float = 0.40

    # ------------------------------------------------------------------
    # Check catalogue
    # ------------------------------------------------------------------

    _CHECKS: list[ScanCheck] = [
        # Branch-protection checks (SEC-001 – SEC-007)
        ScanCheck(
            check_id="SEC-001",
            check_name="Default branch is protected",
            category=Category.security,
            severity=Severity.critical,
            weight=2.0,
            description="The repository default branch must have branch-protection rules enabled.",
        ),
        ScanCheck(
            check_id="SEC-002",
            check_name="PR reviews required",
            category=Category.security,
            severity=Severity.high,
            weight=1.5,
            description="At least one approving review must be required before merging.",
        ),
        ScanCheck(
            check_id="SEC-003",
            check_name="Minimum 2 approvals required",
            category=Category.security,
            severity=Severity.medium,
            weight=1.0,
            description="Two or more approving reviews must be required before merging.",
        ),
        ScanCheck(
            check_id="SEC-004",
            check_name="Stale reviews dismissed on push",
            category=Category.security,
            severity=Severity.medium,
            weight=1.0,
            description="Existing approvals must be dismissed when new commits are pushed.",
        ),
        ScanCheck(
            check_id="SEC-005",
            check_name="Admin enforcement enabled",
            category=Category.security,
            severity=Severity.high,
            weight=1.5,
            description="Branch-protection rules must also apply to repository administrators.",
        ),
        ScanCheck(
            check_id="SEC-006",
            check_name="Force push disabled",
            category=Category.security,
            severity=Severity.high,
            weight=1.5,
            description="Force-pushing to the default branch must be prohibited.",
        ),
        ScanCheck(
            check_id="SEC-007",
            check_name="Signed commits required",
            category=Category.security,
            severity=Severity.low,
            weight=0.5,
            description="All commits merged to the default branch must be GPG-signed.",
        ),
        # Vulnerability / dependency checks (SEC-010 – SEC-014)
        ScanCheck(
            check_id="SEC-010",
            check_name="Dependency scanning enabled",
            category=Category.security,
            severity=Severity.critical,
            weight=2.0,
            description="Dependabot (or equivalent) must be enabled to surface known CVEs.",
        ),
        ScanCheck(
            check_id="SEC-011",
            check_name="No critical vulnerabilities",
            category=Category.security,
            severity=Severity.critical,
            weight=2.0,
            description="The repository must have no open critical-severity vulnerability alerts.",
        ),
        ScanCheck(
            check_id="SEC-012",
            check_name="No high vulnerabilities",
            category=Category.security,
            severity=Severity.high,
            weight=1.5,
            description="The repository must have no open high-severity vulnerability alerts.",
        ),
        ScanCheck(
            check_id="SEC-013",
            check_name="Secret scanning enabled",
            category=Category.security,
            severity=Severity.critical,
            weight=2.0,
            description="Secret scanning must be active to detect accidental credential exposure.",
        ),
        ScanCheck(
            check_id="SEC-014",
            check_name="No exposed secrets",
            category=Category.security,
            severity=Severity.critical,
            weight=2.0,
            description="No open alerts indicating a secret or credential has been leaked.",
        ),
        # Supply-chain / policy checks (SEC-020 – SEC-022)
        ScanCheck(
            check_id="SEC-020",
            check_name="SBOM available",
            category=Category.security,
            severity=Severity.medium,
            weight=1.0,
            description="A Software Bill of Materials must be generated and available.",
        ),
        ScanCheck(
            check_id="SEC-021",
            check_name="Security policy present",
            category=Category.security,
            severity=Severity.medium,
            weight=1.0,
            description="A SECURITY.md (or equivalent) must document the vulnerability-disclosure process.",
        ),
        ScanCheck(
            check_id="SEC-022",
            check_name="CI actions/images pinned",
            category=Category.security,
            severity=Severity.high,
            weight=1.5,
            description=(
                "All referenced CI actions and container images should be pinned to an "
                "immutable digest rather than a mutable tag."
            ),
        ),
    ]

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def checks(self) -> list[ScanCheck]:
        """Return the full catalogue of security checks."""
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every SEC-xxx check against *data* and return one result each."""
        bp: BranchProtection | None = data.branch_protection
        sec: SecurityFeatures | None = data.security
        results: list[CheckResult] = []

        # ---- Branch-protection checks --------------------------------

        check_map = {c.check_id: c for c in self._CHECKS}

        # SEC-001
        check = check_map["SEC-001"]
        if bp is None:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No branch-protection data found."))
        elif bp.is_protected:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="Default branch is protected."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="Default branch protection is not enabled."))

        # SEC-002
        check = check_map["SEC-002"]
        if bp is None:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No branch-protection data found."))
        elif bp.required_reviews >= 1:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail=f"Required approvals: {bp.required_reviews}.",
                    evidence={"required_reviews": bp.required_reviews},
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No PR reviews are required before merging.",
                    evidence={"required_reviews": bp.required_reviews},
                )
            )

        # SEC-003
        check = check_map["SEC-003"]
        if bp is None:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No branch-protection data found."))
        elif bp.required_reviews >= 2:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail=f"Required approvals: {bp.required_reviews}.",
                    evidence={"required_reviews": bp.required_reviews},
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail=f"Only {bp.required_reviews} approval(s) required; minimum is 2.",
                    evidence={"required_reviews": bp.required_reviews},
                )
            )

        # SEC-004
        check = check_map["SEC-004"]
        if bp is None:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No branch-protection data found."))
        elif bp.dismiss_stale_reviews:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="Stale reviews are dismissed on new pushes."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="Stale reviews are not dismissed when new commits are pushed."))

        # SEC-005
        check = check_map["SEC-005"]
        if bp is None:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No branch-protection data found."))
        elif bp.enforce_admins:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="Branch-protection rules are enforced for admins."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="Branch-protection rules are not enforced for administrators."))

        # SEC-006
        check = check_map["SEC-006"]
        if bp is None:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No branch-protection data found."))
        elif not bp.allow_force_pushes:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="Force pushes to the default branch are disabled."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="Force pushes to the default branch are permitted."))

        # SEC-007
        check = check_map["SEC-007"]
        if bp is None:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No branch-protection data found."))
        elif bp.require_signed_commits:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="Signed commits are required."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="Signed commits are not required."))

        # ---- Vulnerability / dependency checks -----------------------

        # SEC-010
        check = check_map["SEC-010"]
        if sec is None:
            results.append(CheckResult(check=check, status=CheckStatus.not_applicable, detail="No security feature data available."))
        elif sec.dependabot_enabled:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="Dependabot dependency scanning is enabled."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="Dependabot dependency scanning is not enabled."))

        # SEC-011
        check = check_map["SEC-011"]
        if sec is None:
            results.append(CheckResult(check=check, status=CheckStatus.not_applicable, detail="No security feature data available."))
        else:
            critical_alerts = [a for a in sec.vulnerability_alerts if a.severity.lower() == "critical"]
            if not critical_alerts:
                results.append(CheckResult(check=check, status=CheckStatus.passed, detail="No open critical-severity vulnerability alerts."))
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"{len(critical_alerts)} open critical-severity vulnerability alert(s) found.",
                        evidence={"critical_alert_count": len(critical_alerts), "packages": [a.package for a in critical_alerts]},
                    )
                )

        # SEC-012
        check = check_map["SEC-012"]
        if sec is None:
            results.append(CheckResult(check=check, status=CheckStatus.not_applicable, detail="No security feature data available."))
        else:
            high_alerts = [a for a in sec.vulnerability_alerts if a.severity.lower() == "high"]
            if not high_alerts:
                results.append(CheckResult(check=check, status=CheckStatus.passed, detail="No open high-severity vulnerability alerts."))
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"{len(high_alerts)} open high-severity vulnerability alert(s) found.",
                        evidence={"high_alert_count": len(high_alerts), "packages": [a.package for a in high_alerts]},
                    )
                )

        # SEC-013
        check = check_map["SEC-013"]
        if sec is None:
            results.append(CheckResult(check=check, status=CheckStatus.not_applicable, detail="No security feature data available."))
        elif sec.secret_scanning_enabled:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="Secret scanning is enabled."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="Secret scanning is not enabled."))

        # SEC-014  (proxy: look for "secret" in an open alert title)
        check = check_map["SEC-014"]
        if sec is None:
            results.append(CheckResult(check=check, status=CheckStatus.not_applicable, detail="No security feature data available."))
        else:
            secret_alerts = [
                a for a in sec.vulnerability_alerts
                if a.state.lower() == "open" and "secret" in a.title.lower()
            ]
            if not secret_alerts:
                results.append(CheckResult(check=check, status=CheckStatus.passed, detail="No open alerts indicating an exposed secret."))
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"{len(secret_alerts)} open alert(s) referencing a potential secret exposure.",
                        evidence={"secret_alert_count": len(secret_alerts), "titles": [a.title for a in secret_alerts]},
                    )
                )

        # ---- Supply-chain / policy checks ----------------------------

        # SEC-020
        check = check_map["SEC-020"]
        if data.has_sbom:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="SBOM artefact is present."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No SBOM artefact was detected."))

        # SEC-021
        check = check_map["SEC-021"]
        if sec is None:
            results.append(CheckResult(check=check, status=CheckStatus.not_applicable, detail="No security feature data available."))
        elif sec.has_security_policy:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="A security policy file is present."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No security policy file (e.g. SECURITY.md) was found."))

        # SEC-022  (always warning — full analysis not available via API)
        check = check_map["SEC-022"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "CI action / container image pinning could not be verified automatically. "
                    "Manual review recommended."
                ),
            )
        )

        return results
