from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData


class SASTScanner(BaseScanner):
    """Evaluates Static Application Security Testing (SAST) practices.

    Category weight: 0.06.
    """

    category: Category = Category.sast
    weight: float = 0.06

    _CHECKS = (
        ScanCheck(
            check_id="SAST-001",
            check_name="SAST tool configured",
            category=Category.sast,
            severity=Severity.high,
            weight=1.5,
            description="A SAST configuration file (e.g. .semgrep.yml, .codeql, sonar-project.properties) must be present.",
        ),
        ScanCheck(
            check_id="SAST-002",
            check_name="SAST runs in CI pipeline",
            category=Category.sast,
            severity=Severity.high,
            weight=1.5,
            description="At least one CI workflow must include a security scan step.",
        ),
        ScanCheck(
            check_id="SAST-003",
            check_name="CodeQL or Semgrep analysis enabled",
            category=Category.sast,
            severity=Severity.medium,
            weight=1.0,
            description="Platform-level code scanning (e.g. GitHub CodeQL) must be enabled for the repository.",
        ),
        ScanCheck(
            check_id="SAST-004",
            check_name="No critical SAST findings",
            category=Category.sast,
            severity=Severity.critical,
            weight=2.0,
            description="The repository must have no open critical-severity SAST findings.",
        ),
        ScanCheck(
            check_id="SAST-005",
            check_name="No high SAST findings",
            category=Category.sast,
            severity=Severity.high,
            weight=1.5,
            description="The repository must have no open high-severity SAST findings.",
        ),
        ScanCheck(
            check_id="SAST-006",
            check_name="Custom SAST rules defined",
            category=Category.sast,
            severity=Severity.low,
            weight=0.5,
            description="Custom rule sets or policies should be defined to extend default SAST coverage.",
        ),
        ScanCheck(
            check_id="SAST-007",
            check_name="SAST results block merge on critical findings",
            category=Category.sast,
            severity=Severity.high,
            weight=1.5,
            description="Critical SAST findings must be configured as required status checks that block pull request merges.",
        ),
        ScanCheck(
            check_id="SAST-008",
            check_name="Incremental scanning enabled",
            category=Category.sast,
            severity=Severity.low,
            weight=0.5,
            description="SAST should be configured to scan only changed files on pull requests for faster feedback.",
        ),
        ScanCheck(
            check_id="SAST-009",
            check_name="Multi-language SAST coverage",
            category=Category.sast,
            severity=Severity.medium,
            weight=1.0,
            description="SAST tooling should cover all primary languages used in the repository.",
        ),
        ScanCheck(
            check_id="SAST-010",
            check_name="False positive management process",
            category=Category.sast,
            severity=Severity.low,
            weight=0.5,
            description="A documented process or suppression mechanism must exist for managing SAST false positives.",
        ),
    )

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every SAST-xxx check against *data* and return one result each."""
        results: list[CheckResult] = []

        # SAST-001: SAST tool configured
        results.append(
            self._bool_check(
                "SAST-001",
                data.has_sast_config,
                passed="A SAST configuration file is present in the repository.",
                failed="No SAST configuration file was detected (e.g. .semgrep.yml, sonar-project.properties).",
            )
        )

        # SAST-002: SAST runs in CI pipeline
        workflows_with_security = [wf for wf in data.ci_workflows if wf.has_security_scan]
        if workflows_with_security:
            results.append(
                CheckResult(
                    check=self._check_map["SAST-002"],
                    status=CheckStatus.passed,
                    detail=f"{len(workflows_with_security)} CI workflow(s) include a security scan step.",
                    evidence={"workflows": [wf.name for wf in workflows_with_security]},
                )
            )
        elif not data.ci_workflows:
            results.append(
                CheckResult(
                    check=self._check_map["SAST-002"],
                    status=CheckStatus.not_applicable,
                    detail="No CI workflows found in the repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["SAST-002"],
                    status=CheckStatus.failed,
                    detail="No CI workflow includes a security scan step.",
                    evidence={"workflow_count": len(data.ci_workflows)},
                )
            )

        # SAST-003: CodeQL/Semgrep analysis enabled (platform code scanning)
        sec = data.security
        if sec is None:
            results.append(
                CheckResult(
                    check=self._check_map["SAST-003"],
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "SAST-003",
                    sec.code_scanning_enabled,
                    passed="Platform code scanning (e.g. CodeQL) is enabled for this repository.",
                    failed="Platform code scanning is not enabled. Consider enabling CodeQL or Semgrep.",
                )
            )

        # SAST-004: No critical SAST findings (cannot verify directly via API)
        results.append(self._manual_review("SAST-004", "Critical SAST findings"))

        # SAST-005: No high SAST findings (cannot verify directly via API)
        results.append(self._manual_review("SAST-005", "High-severity SAST findings"))

        # SAST-006: Custom rules defined (cannot verify directly via API)
        results.append(self._manual_review("SAST-006", "Custom SAST rule definitions"))

        # SAST-007: SAST results block merge on critical (cannot verify directly via API)
        results.append(self._manual_review("SAST-007", "Whether SAST results are configured as required status checks"))

        # SAST-008: Incremental scanning enabled (cannot verify directly via API)
        results.append(self._manual_review("SAST-008", "Incremental SAST scanning configuration"))

        # SAST-009: Multi-language coverage (cannot verify directly via API)
        results.append(self._manual_review("SAST-009", "SAST language coverage"))

        # SAST-010: False positive management (cannot verify directly via API)
        results.append(self._manual_review("SAST-010", "False positive management processes"))

        return results
