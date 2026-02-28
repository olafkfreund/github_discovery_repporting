from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import OrgAssessmentData, OrgSecuritySettings


class PlatformArchScanner(BaseScanner):
    """Evaluates platform-level architecture and organisation-wide configuration.

    Checks cover platform type, enterprise feature availability, default visibility
    policies, IP allow-listing, security policies, and GitHub Advanced Security.

    Category weight: 0.06 (org-level scanner).
    """

    category: Category = Category.platform_arch
    weight: float = 0.06

    # ------------------------------------------------------------------
    # Check catalogue
    # ------------------------------------------------------------------

    _CHECKS = (
        ScanCheck(
            check_id="PLAT-001",
            check_name="Platform type identified",
            category=Category.platform_arch,
            severity=Severity.info,
            weight=0.5,
            description="The source control platform type must be identifiable for accurate assessment.",
        ),
        ScanCheck(
            check_id="PLAT-002",
            check_name="API version supported",
            category=Category.platform_arch,
            severity=Severity.low,
            weight=0.5,
            description="The platform API version must be current and supported for complete data collection.",
        ),
        ScanCheck(
            check_id="PLAT-003",
            check_name="Enterprise features available",
            category=Category.platform_arch,
            severity=Severity.low,
            weight=0.5,
            description="GitHub Enterprise features unlock advanced security controls required for production orgs.",
        ),
        ScanCheck(
            check_id="PLAT-004",
            check_name="Default repository visibility is private",
            category=Category.platform_arch,
            severity=Severity.high,
            weight=1.5,
            description=(
                "The organisation default repository permission must restrict public creation. "
                "Members should not be allowed to create public repositories by default."
            ),
        ),
        ScanCheck(
            check_id="PLAT-005",
            check_name="IP allow-listing enabled",
            category=Category.platform_arch,
            severity=Severity.medium,
            weight=1.0,
            description="IP allow-listing restricts platform access to known corporate network ranges.",
        ),
        ScanCheck(
            check_id="PLAT-006",
            check_name="Org-level security policy exists",
            category=Category.platform_arch,
            severity=Severity.medium,
            weight=1.0,
            description="An organisation-level security policy must be defined and visible to all repositories.",
        ),
        ScanCheck(
            check_id="PLAT-007",
            check_name="GitHub Advanced Security enabled",
            category=Category.platform_arch,
            severity=Severity.high,
            weight=1.5,
            description=(
                "GitHub Advanced Security (GHAS) provides code scanning, secret scanning, and "
                "dependency review across all repositories in the organisation."
            ),
        ),
        ScanCheck(
            check_id="PLAT-008",
            check_name="Audit log streaming configured",
            category=Category.platform_arch,
            severity=Severity.medium,
            weight=1.0,
            description="Audit log streaming must forward platform events to a SIEM or log management system.",
        ),
        ScanCheck(
            check_id="PLAT-009",
            check_name="Custom roles defined",
            category=Category.platform_arch,
            severity=Severity.low,
            weight=0.5,
            description="Custom roles allow fine-grained permission assignment beyond the built-in role set.",
        ),
        ScanCheck(
            check_id="PLAT-010",
            check_name="Self-hosted runners available",
            category=Category.platform_arch,
            severity=Severity.low,
            weight=0.5,
            description="Self-hosted runners give the organisation control over CI build environments and secrets.",
        ),
        ScanCheck(
            check_id="PLAT-011",
            check_name="Actions/runner restrictions configured",
            category=Category.platform_arch,
            severity=Severity.medium,
            weight=1.0,
            description=(
                "GitHub Actions permissions must be restricted to prevent use of arbitrary "
                "third-party actions without review."
            ),
        ),
    )

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def evaluate_org(self, data: OrgAssessmentData) -> list[CheckResult]:
        """Run every PLAT-xxx check against org-level *data* and return one result each."""
        sec: OrgSecuritySettings | None = data.security_settings
        results: list[CheckResult] = []

        # PLAT-001  (always passes — we know the platform is GitHub)
        results.append(
            CheckResult(
                check=self._check_map["PLAT-001"],
                status=CheckStatus.passed,
                detail="Platform identified as GitHub.",
                evidence={"org_name": data.org_name},
            )
        )

        # PLAT-002  (always passes — assessment tool only runs against supported API versions)
        results.append(
            CheckResult(
                check=self._check_map["PLAT-002"],
                status=CheckStatus.passed,
                detail="GitHub REST API v3 / GraphQL v4 is supported and in use.",
            )
        )

        # PLAT-003  (check billing plan string for "enterprise")
        billing_plan = data.billing_plan or ""
        if "enterprise" in billing_plan.lower():
            results.append(
                CheckResult(
                    check=self._check_map["PLAT-003"],
                    status=CheckStatus.passed,
                    detail=f"Enterprise plan detected: '{billing_plan}'.",
                    evidence={"billing_plan": billing_plan},
                )
            )
        else:
            results.append(
                CheckResult(
                    check=self._check_map["PLAT-003"],
                    status=CheckStatus.failed,
                    detail=(
                        f"Billing plan '{billing_plan}' does not include enterprise features. "
                        "Upgrade to GitHub Enterprise to unlock advanced security controls."
                    ),
                    evidence={"billing_plan": billing_plan},
                )
            )

        # PLAT-004  (private-by-default: default_repo_permission not "none" AND
        #            members_can_create_public_repos is False)
        if sec is None:
            results.append(
                CheckResult(
                    check=self._check_map["PLAT-004"],
                    status=CheckStatus.not_applicable,
                    detail="No organisation security settings data available.",
                )
            )
        else:
            allows_public = sec.members_can_create_public_repos
            perm = sec.default_repo_permission or ""
            if not allows_public and perm.lower() != "none":
                results.append(
                    CheckResult(
                        check=self._check_map["PLAT-004"],
                        status=CheckStatus.passed,
                        detail=(
                            "Members cannot create public repositories and a non-permissive "
                            f"default repo permission is set ('{perm}')."
                        ),
                        evidence={
                            "default_repo_permission": perm,
                            "members_can_create_public_repos": allows_public,
                        },
                    )
                )
            else:
                reasons: list[str] = []
                if allows_public:
                    reasons.append("members are allowed to create public repositories")
                if perm.lower() == "none":
                    reasons.append("default repository permission is set to 'none'")
                results.append(
                    CheckResult(
                        check=self._check_map["PLAT-004"],
                        status=CheckStatus.failed,
                        detail="Default repository visibility is not restricted: "
                        + "; ".join(reasons)
                        + ".",
                        evidence={
                            "default_repo_permission": perm,
                            "members_can_create_public_repos": allows_public,
                        },
                    )
                )

        # PLAT-005  (IP allow-listing)
        if sec is None:
            results.append(
                CheckResult(
                    check=self._check_map["PLAT-005"],
                    status=CheckStatus.not_applicable,
                    detail="No organisation security settings data available.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "PLAT-005",
                    sec.ip_allow_list_enabled,
                    passed="IP allow-listing is enabled for the organisation.",
                    failed=(
                        "IP allow-listing is not enabled. Configure an IP allowlist to restrict "
                        "platform access to known corporate network ranges."
                    ),
                )
            )

        # PLAT-006  (org-level security policy)
        results.append(
            self._bool_check(
                "PLAT-006",
                data.has_org_level_security_policy,
                passed="An organisation-level security policy is in place.",
                failed=(
                    "No organisation-level security policy was found. Create a SECURITY.md "
                    "in the .github repository to surface it across all repos."
                ),
            )
        )

        # PLAT-007  (GHAS — cannot verify via standard API; always warning)
        results.append(self._manual_review("PLAT-007", "GitHub Advanced Security enablement"))

        # PLAT-008  (audit log streaming — cannot verify via standard API; always warning)
        results.append(self._manual_review("PLAT-008", "Audit log streaming configuration"))

        # PLAT-009  (custom roles — cannot verify via standard API; always warning)
        results.append(self._manual_review("PLAT-009", "Custom role definitions"))

        # PLAT-010  (self-hosted runners — cannot verify via standard API; always warning)
        results.append(self._manual_review("PLAT-010", "Self-hosted runner availability"))

        # PLAT-011  (Actions/runner restrictions — cannot verify via standard API; always warning)
        results.append(self._manual_review("PLAT-011", "GitHub Actions permission restrictions"))

        return results
