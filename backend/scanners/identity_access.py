from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import OrgAssessmentData, OrgMemberInfo, OrgSecuritySettings


class IdentityAccessScanner(BaseScanner):
    """Evaluates identity and access management practices at the organisation level.

    Checks cover MFA enforcement, SSO, admin ratios, bot account hygiene,
    deploy-key policies, PAT expiry, RBAC scoping, and least-privilege
    verification.

    Several checks cannot be verified through the standard GitHub API and
    therefore always emit a ``warning`` to prompt manual review.

    Category weight: 0.10 (org-level scanner).
    """

    category: Category = Category.identity_access
    weight: float = 0.10

    # ------------------------------------------------------------------
    # Check catalogue
    # ------------------------------------------------------------------

    _CHECKS = (
        ScanCheck(
            check_id="IAM-001",
            check_name="MFA/2FA enforced org-wide",
            category=Category.identity_access,
            severity=Severity.critical,
            weight=2.0,
            description="Multi-factor authentication must be required for every member of the organisation.",
        ),
        ScanCheck(
            check_id="IAM-002",
            check_name="SSO configured",
            category=Category.identity_access,
            severity=Severity.high,
            weight=1.5,
            description="SAML or OIDC single sign-on must be configured to centralise identity management.",
        ),
        ScanCheck(
            check_id="IAM-003",
            check_name="Admin count <= 5% of members",
            category=Category.identity_access,
            severity=Severity.medium,
            weight=1.0,
            description=(
                "The proportion of organisation administrators must not exceed 5% of total "
                "membership to limit blast radius of compromised admin accounts."
            ),
        ),
        ScanCheck(
            check_id="IAM-004",
            check_name="No outside collaborators with admin access",
            category=Category.identity_access,
            severity=Severity.high,
            weight=1.5,
            description="External collaborators must not be granted administrator-level access to any repository.",
        ),
        ScanCheck(
            check_id="IAM-005",
            check_name="Bot accounts use service tokens",
            category=Category.identity_access,
            severity=Severity.medium,
            weight=1.0,
            description="Automated (bot) accounts must authenticate via scoped service tokens, not personal credentials.",
        ),
        ScanCheck(
            check_id="IAM-006",
            check_name="Deploy keys are read-only",
            category=Category.identity_access,
            severity=Severity.high,
            weight=1.5,
            description="Repository deploy keys must be configured as read-only unless write access is explicitly required.",
        ),
        ScanCheck(
            check_id="IAM-007",
            check_name="Personal access tokens have expiry",
            category=Category.identity_access,
            severity=Severity.medium,
            weight=1.0,
            description="All personal access tokens must be issued with an expiration date to limit exposure.",
        ),
        ScanCheck(
            check_id="IAM-008",
            check_name="RBAC roles properly scoped",
            category=Category.identity_access,
            severity=Severity.high,
            weight=1.5,
            description=(
                "Role-based access control assignments must be scoped to the minimum permissions "
                "required for each team or individual."
            ),
        ),
        ScanCheck(
            check_id="IAM-009",
            check_name="Team-based access (not individual)",
            category=Category.identity_access,
            severity=Severity.medium,
            weight=1.0,
            description=(
                "Repository access must be granted to teams rather than individual users to "
                "simplify lifecycle management."
            ),
        ),
        ScanCheck(
            check_id="IAM-010",
            check_name="Inactive users reviewed",
            category=Category.identity_access,
            severity=Severity.low,
            weight=0.5,
            description=(
                "Users who have not accessed the platform recently must be reviewed and "
                "removed or suspended as appropriate."
            ),
        ),
        ScanCheck(
            check_id="IAM-011",
            check_name="Least privilege verified",
            category=Category.identity_access,
            severity=Severity.high,
            weight=1.5,
            description=(
                "The default repository permission for organisation members must follow the "
                "principle of least privilege (read or none)."
            ),
        ),
        ScanCheck(
            check_id="IAM-012",
            check_name="Emergency access procedure exists",
            category=Category.identity_access,
            severity=Severity.medium,
            weight=1.0,
            description=(
                "A documented break-glass procedure must exist for regaining access during "
                "SSO or IdP outages."
            ),
        ),
    )

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def evaluate_org(self, data: OrgAssessmentData) -> list[CheckResult]:
        """Run every IAM-xxx check against org-level *data* and return one result each."""
        members: OrgMemberInfo | None = data.members
        sec: OrgSecuritySettings | None = data.security_settings
        results: list[CheckResult] = []

        # IAM-001  (MFA/2FA enforced)
        if members is None:
            results.append(
                CheckResult(
                    check=self._check_map["IAM-001"],
                    status=CheckStatus.not_applicable,
                    detail="No organisation membership data available.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "IAM-001",
                    members.mfa_enforced,
                    passed="Multi-factor authentication is enforced for all organisation members.",
                    failed=(
                        "MFA/2FA is not enforced organisation-wide. Enable the 'Require two-factor "
                        "authentication' setting in the organisation's security settings."
                    ),
                )
            )

        # IAM-002  (SSO configured)
        if members is None:
            results.append(
                CheckResult(
                    check=self._check_map["IAM-002"],
                    status=CheckStatus.not_applicable,
                    detail="No organisation membership data available.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "IAM-002",
                    members.sso_enabled,
                    passed="SAML/OIDC single sign-on is configured for the organisation.",
                    failed=(
                        "Single sign-on is not configured. Configure SAML or OIDC SSO to "
                        "centralise identity management and enforce corporate authentication policies."
                    ),
                )
            )

        # IAM-003  (admin ratio <= 5%)
        if members is None:
            results.append(
                CheckResult(
                    check=self._check_map["IAM-003"],
                    status=CheckStatus.not_applicable,
                    detail="No organisation membership data available.",
                )
            )
        elif members.total_members == 0:
            results.append(
                CheckResult(
                    check=self._check_map["IAM-003"],
                    status=CheckStatus.not_applicable,
                    detail="Organisation has no members; admin ratio cannot be calculated.",
                )
            )
        else:
            admin_ratio = members.admin_count / members.total_members
            admin_pct = round(admin_ratio * 100, 1)
            evidence = {
                "admin_count": members.admin_count,
                "total_members": members.total_members,
                "admin_ratio_pct": admin_pct,
            }
            if admin_ratio <= 0.05:
                results.append(
                    CheckResult(
                        check=self._check_map["IAM-003"],
                        status=CheckStatus.passed,
                        detail=f"Admin ratio is {admin_pct}% ({members.admin_count}/{members.total_members}), within the 5% threshold.",
                        evidence=evidence,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=self._check_map["IAM-003"],
                        status=CheckStatus.failed,
                        detail=(
                            f"Admin ratio is {admin_pct}% ({members.admin_count}/{members.total_members}), "
                            "exceeding the 5% threshold. Review and reduce the number of organisation admins."
                        ),
                        evidence=evidence,
                    )
                )

        # IAM-004  (outside collaborators with admin — cannot verify via standard API)
        results.append(self._manual_review("IAM-004", "Outside collaborator permission levels"))

        # IAM-005  (bot accounts use service tokens — cannot verify via standard API)
        results.append(self._manual_review("IAM-005", "Bot account authentication methods"))

        # IAM-006  (deploy keys are read-only — cannot verify via standard API)
        results.append(self._manual_review("IAM-006", "Deploy key permissions"))

        # IAM-007  (PAT expiry — cannot verify via standard API)
        results.append(self._manual_review("IAM-007", "Personal access token expiry policies"))

        # IAM-008  (RBAC roles properly scoped — cannot verify via standard API)
        results.append(self._manual_review("IAM-008", "RBAC role scoping"))

        # IAM-009  (team-based access — cannot verify via standard API)
        results.append(self._manual_review("IAM-009", "Whether access is granted via teams or individuals"))

        # IAM-010  (inactive users reviewed — cannot verify via standard API)
        results.append(self._manual_review("IAM-010", "User activity data"))

        # IAM-011  (least privilege: default_repo_permission is "read" or "none")
        if sec is None:
            results.append(
                CheckResult(
                    check=self._check_map["IAM-011"],
                    status=CheckStatus.not_applicable,
                    detail="No organisation security settings data available.",
                )
            )
        else:
            perm = (sec.default_repo_permission or "").lower()
            if perm in ("read", "none"):
                results.append(
                    CheckResult(
                        check=self._check_map["IAM-011"],
                        status=CheckStatus.passed,
                        detail=f"Default repository permission is '{perm}', satisfying the least-privilege requirement.",
                        evidence={"default_repo_permission": perm},
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=self._check_map["IAM-011"],
                        status=CheckStatus.failed,
                        detail=(
                            f"Default repository permission is '{perm}'. Set this to 'read' or 'none' "
                            "to enforce least-privilege access for all organisation members."
                        ),
                        evidence={"default_repo_permission": perm},
                    )
                )

        # IAM-012  (emergency access procedure — cannot verify via standard API)
        results.append(self._manual_review("IAM-012", "The existence of a documented emergency (break-glass) access procedure"))

        return results
