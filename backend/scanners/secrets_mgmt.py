from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData, SecurityFeatures


class SecretsMgmtScanner(BaseScanner):
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

    _CHECKS = (
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
    )

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every SEC-xxx (secrets) check against *data* and return one result each."""
        sec: SecurityFeatures | None = data.security
        results: list[CheckResult] = []

        # SEC-001  (secret scanning enabled)
        if sec is None:
            results.append(
                CheckResult(
                    check=self._check_map["SEC-001"],
                    status=CheckStatus.not_applicable,
                    detail="No security feature data available.",
                )
            )
        else:
            results.append(
                self._bool_check(
                    "SEC-001",
                    sec.secret_scanning_enabled,
                    passed="Secret scanning is enabled for this repository.",
                    failed=(
                        "Secret scanning is not enabled. Enable it in the repository's security "
                        "settings to detect accidental credential exposure."
                    ),
                )
            )

        # SEC-002  (no exposed secrets — proxy via open alerts with "secret" in title)
        if sec is None:
            results.append(
                CheckResult(
                    check=self._check_map["SEC-002"],
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
                        check=self._check_map["SEC-002"],
                        status=CheckStatus.passed,
                        detail="No open alerts indicating an exposed secret were detected.",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check=self._check_map["SEC-002"],
                        status=CheckStatus.failed,
                        detail=f"{len(secret_alerts)} open alert(s) referencing a potential secret exposure.",
                        evidence={
                            "secret_alert_count": len(secret_alerts),
                            "titles": [a.title for a in secret_alerts],
                        },
                    )
                )

        # SEC-003  (push protection — cannot fully verify via standard API)
        results.append(self._manual_review("SEC-003", "Secret scanning push protection status"))

        # SEC-004  (custom secret patterns — cannot verify via standard API)
        results.append(self._manual_review("SEC-004", "Custom secret scanning pattern definitions"))

        # SEC-005  (secrets in vault — cannot verify via standard API)
        results.append(self._manual_review("SEC-005", "Whether runtime secrets are stored in a dedicated vault"))

        # SEC-006  (environment secrets used — cannot verify via standard API)
        results.append(self._manual_review("SEC-006", "CI/CD secret scoping to deployment environments"))

        # SEC-007  (no hardcoded credentials — proxy via secret_scanning_enabled + no open alerts)
        if sec is None:
            results.append(
                CheckResult(
                    check=self._check_map["SEC-007"],
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
                        check=self._check_map["SEC-007"],
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
                        check=self._check_map["SEC-007"],
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
                        check=self._check_map["SEC-007"],
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
        results.append(self._manual_review("SEC-008", "API key rotation policy compliance"))

        # SEC-009  (service accounts use short-lived tokens — cannot verify via standard API)
        results.append(self._manual_review("SEC-009", "Service account token lifetimes"))

        # SEC-010  (secret audit trail — cannot verify via standard API)
        results.append(self._manual_review("SEC-010", "Secret access audit trail availability"))

        return results
