from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData, SecurityFeatures, VulnerabilityAlert


class DependenciesScanner:
    """Evaluates dependency management hygiene for a repository.

    Checks cover automated update tooling (Dependabot/Renovate), open
    vulnerability alerts by severity, lock file presence, dependency pinning,
    licence compliance, SBOM generation, and private registry usage.

    Several checks cannot be fully verified via the standard GitHub API and
    emit a ``warning`` to prompt manual review.

    Category weight: 0.08.
    """

    category: Category = Category.dependencies
    weight: float = 0.08

    # ------------------------------------------------------------------
    # Check catalogue
    # ------------------------------------------------------------------

    _CHECKS: list[ScanCheck] = [
        ScanCheck(
            check_id="DEP-001",
            check_name="Dependabot/Renovate enabled",
            category=Category.dependencies,
            severity=Severity.critical,
            weight=2.0,
            description="Dependabot or Renovate must be configured to surface and auto-PR known CVEs.",
        ),
        ScanCheck(
            check_id="DEP-002",
            check_name="No critical vulnerabilities",
            category=Category.dependencies,
            severity=Severity.critical,
            weight=2.0,
            description="The repository must have no open critical-severity dependency vulnerability alerts.",
        ),
        ScanCheck(
            check_id="DEP-003",
            check_name="No high vulnerabilities",
            category=Category.dependencies,
            severity=Severity.high,
            weight=1.5,
            description="The repository must have no open high-severity dependency vulnerability alerts.",
        ),
        ScanCheck(
            check_id="DEP-004",
            check_name="Lock file present",
            category=Category.dependencies,
            severity=Severity.high,
            weight=1.5,
            description=(
                "A dependency lock file (e.g. package-lock.json, Pipfile.lock, Gemfile.lock) must "
                "be committed to ensure reproducible builds."
            ),
        ),
        ScanCheck(
            check_id="DEP-005",
            check_name="Dependencies pinned to specific versions",
            category=Category.dependencies,
            severity=Severity.medium,
            weight=1.0,
            description=(
                "All direct dependencies must be pinned to exact or narrow version ranges to prevent "
                "unexpected upstream changes."
            ),
        ),
        ScanCheck(
            check_id="DEP-006",
            check_name="Licence compliance checked",
            category=Category.dependencies,
            severity=Severity.medium,
            weight=1.0,
            description="Dependency licences must be reviewed to ensure compatibility with the project's licence.",
        ),
        ScanCheck(
            check_id="DEP-007",
            check_name="Dependency update PRs auto-created",
            category=Category.dependencies,
            severity=Severity.medium,
            weight=1.0,
            description="Automated tooling must open pull requests for dependency updates without manual intervention.",
        ),
        ScanCheck(
            check_id="DEP-008",
            check_name="Outdated dependencies addressed within 30 days",
            category=Category.dependencies,
            severity=Severity.medium,
            weight=1.0,
            description="Open dependency update pull requests must be merged or dismissed within 30 days of creation.",
        ),
        ScanCheck(
            check_id="DEP-009",
            check_name="SBOM generated",
            category=Category.dependencies,
            severity=Severity.medium,
            weight=1.0,
            description=(
                "A Software Bill of Materials (SBOM) must be generated and published to enable "
                "supply-chain risk assessment."
            ),
        ),
        ScanCheck(
            check_id="DEP-010",
            check_name="No deprecated dependencies",
            category=Category.dependencies,
            severity=Severity.low,
            weight=0.5,
            description="Dependencies that have been officially deprecated or abandoned must be replaced.",
        ),
        ScanCheck(
            check_id="DEP-011",
            check_name="Private registry used for internal packages",
            category=Category.dependencies,
            severity=Severity.low,
            weight=0.5,
            description=(
                "Internal or proprietary packages must be served from a private registry to prevent "
                "dependency confusion attacks."
            ),
        ),
    ]

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def checks(self) -> list[ScanCheck]:
        """Return the full catalogue of dependency management checks."""
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every DEP-xxx check against *data* and return one result each."""
        sec: SecurityFeatures | None = data.security
        results: list[CheckResult] = []
        check_map = {c.check_id: c for c in self._CHECKS}

        # DEP-001  (Dependabot/Renovate enabled)
        check = check_map["DEP-001"]
        if sec is None:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        elif sec.dependabot_enabled:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="Dependabot dependency scanning and update automation is enabled.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail=(
                        "Dependabot is not enabled. Configure Dependabot or Renovate to automatically "
                        "surface and patch known vulnerabilities in dependencies."
                    ),
                )
            )

        # DEP-002  (no critical vulnerabilities)
        check = check_map["DEP-002"]
        if sec is None:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        else:
            critical_alerts: list[VulnerabilityAlert] = [
                a for a in sec.vulnerability_alerts if a.severity.lower() == "critical"
            ]
            if not critical_alerts:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.passed,
                        detail="No open critical-severity vulnerability alerts.",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"{len(critical_alerts)} open critical-severity vulnerability alert(s) found.",
                        evidence={
                            "critical_alert_count": len(critical_alerts),
                            "packages": [a.package for a in critical_alerts],
                        },
                    )
                )

        # DEP-003  (no high vulnerabilities)
        check = check_map["DEP-003"]
        if sec is None:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        else:
            high_alerts: list[VulnerabilityAlert] = [
                a for a in sec.vulnerability_alerts if a.severity.lower() == "high"
            ]
            if not high_alerts:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.passed,
                        detail="No open high-severity vulnerability alerts.",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"{len(high_alerts)} open high-severity vulnerability alert(s) found.",
                        evidence={
                            "high_alert_count": len(high_alerts),
                            "packages": [a.package for a in high_alerts],
                        },
                    )
                )

        # DEP-004  (lock file present — not reliably detectable via standard API)
        check = check_map["DEP-004"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Lock file presence cannot be reliably detected via the repository API. "
                    "Manual confirmation that a dependency lock file is committed is recommended."
                ),
            )
        )

        # DEP-005  (dependencies pinned — cannot verify via standard API)
        check = check_map["DEP-005"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Dependency version pinning cannot be verified automatically via the standard API. "
                    "Manual review of the dependency manifest files is recommended."
                ),
            )
        )

        # DEP-006  (licence compliance — cannot verify via standard API)
        check = check_map["DEP-006"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Licence compatibility analysis is not available via the standard API. "
                    "Manual review using a licence scanning tool (e.g. FOSSA, Licensee) is recommended."
                ),
            )
        )

        # DEP-007  (dependency update PRs auto-created — same signal as DEP-001)
        check = check_map["DEP-007"]
        if sec is None:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        elif sec.dependabot_enabled:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="Dependabot is enabled and will automatically open pull requests for dependency updates.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail=(
                        "No automated dependency update tooling is enabled. Configure Dependabot or "
                        "Renovate to open pull requests for outdated or vulnerable dependencies."
                    ),
                )
            )

        # DEP-008  (outdated dependencies addressed within 30 days — cannot verify via standard API)
        check = check_map["DEP-008"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "The age of open dependency update pull requests cannot be determined automatically. "
                    "Manual review to ensure dependency PRs are merged or dismissed within 30 days is recommended."
                ),
            )
        )

        # DEP-009  (SBOM generated)
        check = check_map["DEP-009"]
        if data.has_sbom:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="An SBOM artefact is present in the repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail=(
                        "No SBOM artefact was detected. Generate and publish an SBOM (e.g. via "
                        "GitHub's dependency graph export or a tool such as Syft/CycloneDX)."
                    ),
                )
            )

        # DEP-010  (no deprecated dependencies — cannot verify via standard API)
        check = check_map["DEP-010"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Deprecated dependency detection is not available via the standard API. "
                    "Manual review using a dependency analysis tool is recommended."
                ),
            )
        )

        # DEP-011  (private registry for internal packages — cannot verify via standard API)
        check = check_map["DEP-011"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Private registry usage for internal packages cannot be verified automatically. "
                    "Manual confirmation that internal packages are served from a private registry "
                    "(e.g. GitHub Packages, Artifactory) is recommended."
                ),
            )
        )

        return results
