from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData


class GovernanceScanner:
    """Evaluates governance, compliance, and access-control practices.

    Several checks in this category cannot be verified through the standard
    repository API alone (e.g. MFA enforcement, audit logging) and therefore
    always emit a ``warning`` to prompt manual review.

    Category weight: 0.10.
    """

    category: Category = Category.governance
    weight: float = 0.10

    _CHECKS: list[ScanCheck] = [
        ScanCheck(
            check_id="GOV-001",
            check_name="RBAC configured",
            category=Category.governance,
            severity=Severity.high,
            weight=1.5,
            description="Role-based access control must be configured to limit repository permissions.",
        ),
        ScanCheck(
            check_id="GOV-002",
            check_name="Audit logging available",
            category=Category.governance,
            severity=Severity.medium,
            weight=1.0,
            description="Platform audit logging must be enabled to provide an activity trail.",
        ),
        ScanCheck(
            check_id="GOV-003",
            check_name="MFA enforced",
            category=Category.governance,
            severity=Severity.high,
            weight=1.5,
            description="Multi-factor authentication must be required for all organisation members.",
        ),
        ScanCheck(
            check_id="GOV-004",
            check_name="LICENSE file present",
            category=Category.governance,
            severity=Severity.low,
            weight=0.5,
            description="A LICENSE file must clearly state the terms under which the code may be used.",
        ),
        ScanCheck(
            check_id="GOV-005",
            check_name="Compliance frameworks assigned",
            category=Category.governance,
            severity=Severity.medium,
            weight=1.0,
            description="The repository should be tagged with the compliance frameworks it must satisfy.",
        ),
    ]

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def checks(self) -> list[ScanCheck]:
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        check_map = {c.check_id: c for c in self._CHECKS}
        results: list[CheckResult] = []

        # GOV-001  (RBAC — not verifiable per-repo via standard API)
        check = check_map["GOV-001"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "RBAC configuration could not be verified automatically via the repository API. "
                    "Manual review of team permissions and access levels is recommended."
                ),
            )
        )

        # GOV-002  (audit logging — organisation/platform-level setting)
        check = check_map["GOV-002"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Audit logging is a platform-level setting and cannot be verified at the "
                    "repository level. Manual review recommended."
                ),
            )
        )

        # GOV-003  (MFA — organisation-level setting)
        check = check_map["GOV-003"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "MFA enforcement is an organisation-level setting and cannot be verified "
                    "via the repository API. Manual review recommended."
                ),
            )
        )

        # GOV-004
        check = check_map["GOV-004"]
        if data.has_license:
            results.append(CheckResult(check=check, status=CheckStatus.passed, detail="A LICENSE file is present."))
        else:
            results.append(CheckResult(check=check, status=CheckStatus.failed, detail="No LICENSE file was found in the repository."))

        # GOV-005  (compliance-framework tagging — not detectable via standard API)
        check = check_map["GOV-005"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Compliance-framework assignment is platform-specific and could not be "
                    "verified automatically. Manual review recommended."
                ),
            )
        )

        return results
