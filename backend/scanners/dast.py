from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData


class DASTScanner(BaseScanner):
    """Evaluates Dynamic Application Security Testing (DAST) practices.

    Category weight: 0.04.
    """

    category: Category = Category.dast
    weight: float = 0.04

    _CHECKS = (
        ScanCheck(
            check_id="DAST-001",
            check_name="DAST tool configured",
            category=Category.dast,
            severity=Severity.medium,
            weight=1.0,
            description="A DAST configuration file (e.g. ZAP config, Burp Suite project) must be present.",
        ),
        ScanCheck(
            check_id="DAST-002",
            check_name="DAST runs in CI/CD pipeline",
            category=Category.dast,
            severity=Severity.medium,
            weight=1.0,
            description="Dynamic security testing must be integrated into the CI/CD pipeline.",
        ),
        ScanCheck(
            check_id="DAST-003",
            check_name="API security testing enabled",
            category=Category.dast,
            severity=Severity.medium,
            weight=1.0,
            description="API-level dynamic security testing (e.g. OpenAPI fuzzing) must be configured.",
        ),
        ScanCheck(
            check_id="DAST-004",
            check_name="No critical DAST findings",
            category=Category.dast,
            severity=Severity.high,
            weight=1.5,
            description="The application must have no open critical-severity DAST findings.",
        ),
        ScanCheck(
            check_id="DAST-005",
            check_name="Authenticated scanning configured",
            category=Category.dast,
            severity=Severity.medium,
            weight=1.0,
            description="DAST scans must be configured to run in an authenticated context to reach protected endpoints.",
        ),
        ScanCheck(
            check_id="DAST-006",
            check_name="OWASP Top 10 coverage",
            category=Category.dast,
            severity=Severity.high,
            weight=1.5,
            description="DAST tooling must cover all OWASP Top 10 vulnerability categories.",
        ),
        ScanCheck(
            check_id="DAST-007",
            check_name="Regular DAST scan schedule",
            category=Category.dast,
            severity=Severity.low,
            weight=0.5,
            description="DAST scans must be scheduled to run on a regular cadence against staging or production environments.",
        ),
        ScanCheck(
            check_id="DAST-008",
            check_name="DAST results integrated with issue tracker",
            category=Category.dast,
            severity=Severity.low,
            weight=0.5,
            description="DAST findings must be automatically imported into the project issue tracker for triage.",
        ),
    )

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every DAST-xxx check against *data* and return one result each."""
        results: list[CheckResult] = []

        # DAST-001: DAST tool configured
        results.append(
            self._bool_check(
                "DAST-001",
                data.has_dast_config,
                passed="A DAST configuration file is present in the repository.",
                failed="No DAST configuration file was detected (e.g. ZAP config, Burp project file).",
            )
        )

        # DAST-002: DAST runs in pipeline (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["DAST-002"],
                status=CheckStatus.warning,
                detail=(
                    "DAST pipeline integration could not be verified automatically. "
                    "Confirm that dynamic security testing is executed within the CI/CD pipeline."
                ),
            )
        )

        # DAST-003: API security testing enabled (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["DAST-003"],
                status=CheckStatus.warning,
                detail=(
                    "API security testing configuration could not be verified automatically. "
                    "Confirm that API-level dynamic testing (e.g. OpenAPI fuzzing) is configured."
                ),
            )
        )

        # DAST-004: No critical DAST findings (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["DAST-004"],
                status=CheckStatus.warning,
                detail=(
                    "Critical DAST findings could not be verified automatically. "
                    "Manual review of DAST scan reports is recommended."
                ),
            )
        )

        # DAST-005: Authenticated scanning configured (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["DAST-005"],
                status=CheckStatus.warning,
                detail=(
                    "Authenticated DAST scanning configuration could not be verified automatically. "
                    "Confirm that scans are executed with valid session credentials."
                ),
            )
        )

        # DAST-006: OWASP Top 10 coverage (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["DAST-006"],
                status=CheckStatus.warning,
                detail=(
                    "OWASP Top 10 coverage could not be verified automatically. "
                    "Confirm that the configured DAST tool covers all OWASP Top 10 categories."
                ),
            )
        )

        # DAST-007: Regular scan schedule (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["DAST-007"],
                status=CheckStatus.warning,
                detail=(
                    "DAST scan scheduling could not be verified automatically. "
                    "Confirm that recurring DAST scans are scheduled against a stable environment."
                ),
            )
        )

        # DAST-008: DAST results integrated with issue tracker (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["DAST-008"],
                status=CheckStatus.warning,
                detail=(
                    "DAST-to-issue-tracker integration could not be verified automatically. "
                    "Confirm that scan findings are automatically imported for triage and remediation."
                ),
            )
        )

        return results
