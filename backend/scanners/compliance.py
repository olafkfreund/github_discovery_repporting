from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData


class ComplianceScanner(BaseScanner):
    """Evaluates compliance and audit readiness for a repository.

    Category weight: 0.06.
    """

    category: Category = Category.compliance
    weight: float = 0.06

    _CHECKS = (
        ScanCheck(
            check_id="COMP-001",
            check_name="LICENSE file present",
            category=Category.compliance,
            severity=Severity.low,
            weight=0.5,
            description="A LICENSE file must be present to declare the terms under which the software is distributed.",
        ),
        ScanCheck(
            check_id="COMP-002",
            check_name="Audit logging available",
            category=Category.compliance,
            severity=Severity.medium,
            weight=1.0,
            description="Audit logging must be enabled or configured to capture significant system and user events.",
        ),
        ScanCheck(
            check_id="COMP-003",
            check_name="Compliance frameworks assigned",
            category=Category.compliance,
            severity=Severity.medium,
            weight=1.0,
            description="Applicable compliance frameworks (e.g. SOC 2, ISO 27001, PCI DSS) must be documented.",
        ),
        ScanCheck(
            check_id="COMP-004",
            check_name="Security policy present",
            category=Category.compliance,
            severity=Severity.medium,
            weight=1.0,
            description="A security policy file (e.g. SECURITY.md) must document the vulnerability disclosure process.",
        ),
        ScanCheck(
            check_id="COMP-005",
            check_name="Data classification labels used",
            category=Category.compliance,
            severity=Severity.medium,
            weight=1.0,
            description="Data classification labels must be applied to repositories and artefacts to enforce handling controls.",
        ),
        ScanCheck(
            check_id="COMP-006",
            check_name="Data retention policy defined",
            category=Category.compliance,
            severity=Severity.low,
            weight=0.5,
            description="A data retention policy must be defined and applied to logs, backups, and sensitive data.",
        ),
        ScanCheck(
            check_id="COMP-007",
            check_name="Change management process documented",
            category=Category.compliance,
            severity=Severity.medium,
            weight=1.0,
            description="A changelog or change management document must record significant changes for audit traceability.",
        ),
        ScanCheck(
            check_id="COMP-008",
            check_name="Vendor risk assessment available",
            category=Category.compliance,
            severity=Severity.low,
            weight=0.5,
            description="A vendor or third-party risk assessment must be available for all external dependencies.",
        ),
        ScanCheck(
            check_id="COMP-009",
            check_name="Compliance scanning in pipeline",
            category=Category.compliance,
            severity=Severity.medium,
            weight=1.0,
            description="Automated compliance checks (e.g. licence scanning, policy-as-code) must run in the CI/CD pipeline.",
        ),
        ScanCheck(
            check_id="COMP-010",
            check_name="Regulatory mapping documented",
            category=Category.compliance,
            severity=Severity.low,
            weight=0.5,
            description="Controls must be mapped to specific regulatory requirements to support audit evidence collection.",
        ),
        ScanCheck(
            check_id="COMP-011",
            check_name="Evidence collection automated",
            category=Category.compliance,
            severity=Severity.medium,
            weight=1.0,
            description="Compliance evidence (logs, reports, artefacts) must be collected automatically as part of the pipeline.",
        ),
    )

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every COMP-xxx check against *data* and return one result each."""
        results: list[CheckResult] = []

        # COMP-001: LICENSE file present
        results.append(
            self._bool_check(
                "COMP-001",
                data.has_license,
                passed="A LICENSE file is present in the repository.",
                failed="No LICENSE file was found. Add a LICENSE to declare distribution terms.",
            )
        )

        # COMP-002: Audit logging available (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["COMP-002"],
                status=CheckStatus.warning,
                detail=(
                    "Audit logging configuration could not be verified automatically. "
                    "Confirm that platform-level audit logs are enabled and retained for the required period."
                ),
            )
        )

        # COMP-003: Compliance frameworks assigned (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["COMP-003"],
                status=CheckStatus.warning,
                detail=(
                    "Compliance framework assignments could not be verified automatically. "
                    "Confirm that applicable frameworks (e.g. SOC 2, ISO 27001) are documented for this repository."
                ),
            )
        )

        # COMP-004: Security policy present
        sec = data.security
        if sec is None:
            results.append(
                CheckResult(
                    check=self._check_map["COMP-004"],
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "COMP-004",
                    sec.has_security_policy,
                    passed="A security policy file is present.",
                    failed="No security policy file (e.g. SECURITY.md) was found.",
                )
            )

        # COMP-005: Data classification labels used (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["COMP-005"],
                status=CheckStatus.warning,
                detail=(
                    "Data classification label usage could not be verified automatically. "
                    "Confirm that repository topics, labels, or documentation reflect the appropriate data classification."
                ),
            )
        )

        # COMP-006: Data retention policy defined (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["COMP-006"],
                status=CheckStatus.warning,
                detail=(
                    "Data retention policy definitions could not be verified automatically. "
                    "Confirm that a retention policy is documented and enforced for logs and sensitive artefacts."
                ),
            )
        )

        # COMP-007: Change management process documented (changelog as proxy)
        results.append(
            self._bool_check(
                "COMP-007",
                data.has_changelog,
                passed="A changelog file is present, providing a record of significant changes.",
                failed="No changelog was detected. Add a CHANGELOG to maintain an audit trail of changes.",
            )
        )

        # COMP-008: Vendor risk assessment available (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["COMP-008"],
                status=CheckStatus.warning,
                detail=(
                    "Vendor risk assessment availability could not be verified automatically. "
                    "Confirm that third-party dependency risk assessments are documented and reviewed regularly."
                ),
            )
        )

        # COMP-009: Compliance scanning in pipeline (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["COMP-009"],
                status=CheckStatus.warning,
                detail=(
                    "Compliance scanning pipeline integration could not be verified automatically. "
                    "Confirm that licence scanning, policy-as-code, or similar compliance tooling runs in CI/CD."
                ),
            )
        )

        # COMP-010: Regulatory mapping documented (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["COMP-010"],
                status=CheckStatus.warning,
                detail=(
                    "Regulatory control mapping could not be verified automatically. "
                    "Confirm that implemented controls are mapped to specific regulatory requirements."
                ),
            )
        )

        # COMP-011: Evidence collection automated (cannot verify directly via API)
        results.append(
            CheckResult(
                check=self._check_map["COMP-011"],
                status=CheckStatus.warning,
                detail=(
                    "Automated evidence collection could not be verified automatically. "
                    "Confirm that compliance artefacts (reports, logs, scan results) are automatically gathered and stored."
                ),
            )
        )

        return results
