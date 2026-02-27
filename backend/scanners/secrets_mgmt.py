from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData, SecurityFeatures


class SecretsMgmtScanner:
    """Evaluates secrets management practices for a repository.

    Checks cover secret scanning enablement, detected secret exposures, push
    protection, vault usage, and credential hygiene.  Several checks cannot be
    fully verified via the standard GitHub API and emit a ``warning`` to prompt
    manual review.

    Category weight: 0.08.
    """

    category: Category = Category.secrets_mgmt
    weight: float = 0.08

    # ------------------------------------------------------------------
    # Check catalogue
    # ------------------------------------------------------------------

    _CHECKS: list[ScanCheck] = [
        ScanCheck(
            check_id="SEC-001",
            check_name="Secret scanning enabled",
            category=Category.secrets_mgmt,
            severity=Severity.critical,
            weight=2.0,
            description="GitHub secret scanning must be active to detect accidental credential exposure in commits.",
        ),
        ScanCheck(
            check_id="SEC-002",
            check_name="No exposed secrets detected",
            category=Category.secrets_mgmt,
            severity=Severity.critical,
            weight=2.0,
            description="No open alerts indicating a secret or credential has been leaked into the repository.",
        ),
        ScanCheck(
            check_id="SEC-003",
            check_name="Push protection enabled",
            category=Category.secrets_mgmt,
            severity=Severity.critical,
            weight=2.0,
            description="Secret scanning push protection must block commits containing known secret patterns before they land.",
        ),
        ScanCheck(
            check_id="SEC-004",
            check_name="Custom secret patterns defined",
            category=Category.secrets_mgmt,
            severity=Severity.medium,
            weight=1.0,
            description="Custom secret scanning patterns must cover organisation-specific token formats not detected by default.",
        ),
        ScanCheck(
            check_id="SEC-005",
            check_name="Secrets stored in vault (not repository)",
            category=Category.secrets_mgmt,
            severity=Severity.high,
            weight=1.5,
            description="All runtime secrets must be stored in a dedicated secrets manager (e.g. HashiCorp Vault, AWS Secrets Manager).",
        ),
        ScanCheck(
            check_id="SEC-006",
            check_name="Environment secrets used for deployments",
            category=Category.secrets_mgmt,
            severity=Severity.medium,
            weight=1.0,
            description="CI/CD secrets must be scoped to deployment environments rather than stored at the repository level.",
        ),
        ScanCheck(
            check_id="SEC-007",
            check_name="No hardcoded credentials in code",
            category=Category.secrets_mgmt,
            severity=Severity.critical,
            weight=2.0,
            description="The codebase must contain no hardcoded passwords, API keys, or other credentials.",
        ),
        ScanCheck(
            check_id="SEC-008",
            check_name="API keys have rotation policy",
            category=Category.secrets_mgmt,
            severity=Severity.medium,
            weight=1.0,
            description="All API keys and long-lived tokens must be subject to a documented rotation schedule.",
        ),
        ScanCheck(
            check_id="SEC-009",
            check_name="Service accounts use short-lived tokens",
            category=Category.secrets_mgmt,
            severity=Severity.medium,
            weight=1.0,
            description="Service accounts must authenticate with short-lived, scoped tokens (e.g. OIDC) rather than long-lived keys.",
        ),
        ScanCheck(
            check_id="SEC-010",
            check_name="Secret audit trail available",
            category=Category.secrets_mgmt,
            severity=Severity.low,
            weight=0.5,
            description="Access to secrets must generate an auditable trail of who retrieved what and when.",
        ),
    ]

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def checks(self) -> list[ScanCheck]:
        """Return the full catalogue of secrets management checks."""
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every SEC-xxx (secrets) check against *data* and return one result each."""
        sec: SecurityFeatures | None = data.security
        results: list[CheckResult] = []
        check_map = {c.check_id: c for c in self._CHECKS}

        # SEC-001  (secret scanning enabled)
        check = check_map["SEC-001"]
        if sec is None:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        elif sec.secret_scanning_enabled:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="Secret scanning is enabled for this repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail=(
                        "Secret scanning is not enabled. Enable it in the repository's security "
                        "settings to detect accidental credential exposure."
                    ),
                )
            )

        # SEC-002  (no exposed secrets — proxy via open alerts with "secret" in title)
        check = check_map["SEC-002"]
        if sec is None:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        else:
            secret_alerts = [
                a
                for a in sec.vulnerability_alerts
                if a.state.lower() == "open" and "secret" in a.title.lower()
            ]
            if not secret_alerts:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.passed,
                        detail="No open alerts indicating an exposed secret were detected.",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=f"{len(secret_alerts)} open alert(s) referencing a potential secret exposure.",
                        evidence={
                            "secret_alert_count": len(secret_alerts),
                            "titles": [a.title for a in secret_alerts],
                        },
                    )
                )

        # SEC-003  (push protection — cannot fully verify via standard API)
        check = check_map["SEC-003"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Secret scanning push protection status cannot be fully verified via the "
                    "standard API. Manual confirmation that push protection is enabled is recommended."
                ),
            )
        )

        # SEC-004  (custom secret patterns — cannot verify via standard API)
        check = check_map["SEC-004"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Custom secret scanning pattern definitions cannot be enumerated via the "
                    "standard API. Manual review of the organisation's custom patterns is recommended."
                ),
            )
        )

        # SEC-005  (secrets in vault — cannot verify via standard API)
        check = check_map["SEC-005"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Whether runtime secrets are stored in a dedicated vault cannot be verified "
                    "automatically. Manual review of secrets management practices is recommended."
                ),
            )
        )

        # SEC-006  (environment secrets used — cannot verify via standard API)
        check = check_map["SEC-006"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "CI/CD secret scoping to deployment environments cannot be verified "
                    "automatically. Manual review of GitHub Actions environment secrets is recommended."
                ),
            )
        )

        # SEC-007  (no hardcoded credentials — proxy via secret_scanning_enabled + no open alerts)
        check = check_map["SEC-007"]
        if sec is None:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        else:
            secret_alerts = [
                a
                for a in sec.vulnerability_alerts
                if a.state.lower() == "open" and "secret" in a.title.lower()
            ]
            if sec.secret_scanning_enabled and not secret_alerts:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.passed,
                        detail=(
                            "Secret scanning is enabled and no open secret alerts were found, "
                            "suggesting no hardcoded credentials are present."
                        ),
                    )
                )
            elif not sec.secret_scanning_enabled:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=(
                            "Secret scanning is disabled; hardcoded credentials cannot be detected. "
                            "Enable secret scanning and perform a full repository audit."
                        ),
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=check,
                        status=CheckStatus.failed,
                        detail=(
                            f"{len(secret_alerts)} open secret alert(s) indicate potential hardcoded "
                            "credentials. Rotate the exposed secrets and remove them from the codebase."
                        ),
                        evidence={
                            "secret_alert_count": len(secret_alerts),
                            "titles": [a.title for a in secret_alerts],
                        },
                    )
                )

        # SEC-008  (API key rotation policy — cannot verify via standard API)
        check = check_map["SEC-008"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "API key rotation policy compliance cannot be verified automatically. "
                    "Manual review to confirm all API keys have a documented rotation schedule is recommended."
                ),
            )
        )

        # SEC-009  (service accounts use short-lived tokens — cannot verify via standard API)
        check = check_map["SEC-009"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Service account token lifetimes cannot be verified via the standard API. "
                    "Manual review to confirm short-lived tokens (e.g. OIDC) are used in CI/CD is recommended."
                ),
            )
        )

        # SEC-010  (secret audit trail — cannot verify via standard API)
        check = check_map["SEC-010"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Secret access audit trail availability cannot be verified automatically. "
                    "Manual confirmation that the secrets management system provides an audit log is recommended."
                ),
            )
        )

        return results
