from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData


class ContainerSecurityScanner:
    """Evaluates container security practices for repositories that use Docker.

    When no Dockerfile is detected (CNTR-001 fails), all subsequent container
    checks are marked as not_applicable since they have no relevant surface area.

    Category weight: 0.06.
    """

    category: Category = Category.container_security
    weight: float = 0.06

    _CHECKS: list[ScanCheck] = [
        ScanCheck(
            check_id="CNTR-001",
            check_name="Dockerfile present",
            category=Category.container_security,
            severity=Severity.medium,
            weight=1.0,
            description="A Dockerfile must be present to containerise the application.",
        ),
        ScanCheck(
            check_id="CNTR-002",
            check_name="Base image from trusted registry",
            category=Category.container_security,
            severity=Severity.high,
            weight=1.5,
            description="Container base images must be sourced from a trusted, official registry.",
        ),
        ScanCheck(
            check_id="CNTR-003",
            check_name="Base image pinned by digest",
            category=Category.container_security,
            severity=Severity.high,
            weight=1.5,
            description="Base images must be pinned to an immutable SHA256 digest rather than a mutable tag.",
        ),
        ScanCheck(
            check_id="CNTR-004",
            check_name="Multi-stage build used",
            category=Category.container_security,
            severity=Severity.medium,
            weight=1.0,
            description="Multi-stage Docker builds should be used to minimise the final image attack surface.",
        ),
        ScanCheck(
            check_id="CNTR-005",
            check_name="Container does not run as root",
            category=Category.container_security,
            severity=Severity.critical,
            weight=2.0,
            description="The container entrypoint must run as a non-root user to limit privilege escalation risk.",
        ),
        ScanCheck(
            check_id="CNTR-006",
            check_name="Container image scanning in pipeline",
            category=Category.container_security,
            severity=Severity.high,
            weight=1.5,
            description="Container images must be scanned for known CVEs as part of the CI/CD pipeline.",
        ),
        ScanCheck(
            check_id="CNTR-007",
            check_name="No secrets embedded in Dockerfile",
            category=Category.container_security,
            severity=Severity.critical,
            weight=2.0,
            description="Secrets, API keys, or credentials must not be baked into the Dockerfile or image layers.",
        ),
        ScanCheck(
            check_id="CNTR-008",
            check_name="Container health check defined",
            category=Category.container_security,
            severity=Severity.medium,
            weight=1.0,
            description="A HEALTHCHECK instruction must be defined to enable runtime health monitoring.",
        ),
        ScanCheck(
            check_id="CNTR-009",
            check_name="Read-only root filesystem",
            category=Category.container_security,
            severity=Severity.medium,
            weight=1.0,
            description="Containers should be configured to run with a read-only root filesystem where possible.",
        ),
        ScanCheck(
            check_id="CNTR-010",
            check_name="Resource limits defined",
            category=Category.container_security,
            severity=Severity.medium,
            weight=1.0,
            description="CPU and memory resource limits must be defined for container deployments.",
        ),
        ScanCheck(
            check_id="CNTR-011",
            check_name="Container image signing enabled",
            category=Category.container_security,
            severity=Severity.medium,
            weight=1.0,
            description="Container images must be signed (e.g. with Cosign or Notary) to ensure integrity.",
        ),
        ScanCheck(
            check_id="CNTR-012",
            check_name="Runtime security policy defined",
            category=Category.container_security,
            severity=Severity.low,
            weight=0.5,
            description="A runtime security policy (e.g. seccomp, AppArmor, Pod Security Standards) must be defined.",
        ),
    ]

    def checks(self) -> list[ScanCheck]:
        """Return the full catalogue of container security checks."""
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every CNTR-xxx check against *data* and return one result each.

        If CNTR-001 determines no Dockerfile is present, all remaining checks
        are marked ``not_applicable`` since there is no container surface area
        to evaluate.
        """
        check_map = {c.check_id: c for c in self._CHECKS}
        results: list[CheckResult] = []

        # CNTR-001: Dockerfile present
        check = check_map["CNTR-001"]
        has_dockerfile = data.has_dockerfile
        if has_dockerfile:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A Dockerfile is present in the repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No Dockerfile was detected. Container security checks are not applicable.",
                )
            )

        # All remaining checks are not_applicable when no Dockerfile exists.
        _na_detail = "Not applicable: no Dockerfile detected in this repository."

        # CNTR-002: Base image from trusted registry
        check = check_map["CNTR-002"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Base image registry trust could not be verified automatically. "
                        "Confirm that all base images originate from official or organisation-approved registries."
                    ),
                )
            )

        # CNTR-003: Base image pinned by digest
        check = check_map["CNTR-003"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Base image digest pinning could not be verified automatically. "
                        "Confirm that FROM instructions reference images by SHA256 digest rather than a tag."
                    ),
                )
            )

        # CNTR-004: Multi-stage build used
        check = check_map["CNTR-004"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Multi-stage build usage could not be verified automatically. "
                        "Confirm that the Dockerfile uses multi-stage builds to reduce the final image size."
                    ),
                )
            )

        # CNTR-005: No root user in container
        check = check_map["CNTR-005"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Container user context could not be verified automatically. "
                        "Confirm that the Dockerfile includes a USER instruction to run as a non-root user."
                    ),
                )
            )

        # CNTR-006: Image scanning in pipeline
        check = check_map["CNTR-006"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        elif data.has_container_scanning:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="Container image scanning is configured in the CI/CD pipeline.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No container image scanning was detected in the CI/CD pipeline.",
                )
            )

        # CNTR-007: No secrets in Dockerfile
        check = check_map["CNTR-007"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Secret embedding in the Dockerfile could not be verified automatically. "
                        "Confirm that no credentials, tokens, or keys are present in Dockerfile instructions or build args."
                    ),
                )
            )

        # CNTR-008: Health check defined
        check = check_map["CNTR-008"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Dockerfile HEALTHCHECK instruction could not be verified automatically. "
                        "Confirm that a HEALTHCHECK is defined to enable container runtime health monitoring."
                    ),
                )
            )

        # CNTR-009: Read-only filesystem
        check = check_map["CNTR-009"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Read-only root filesystem configuration could not be verified automatically. "
                        "Confirm that runtime orchestration enforces a read-only filesystem where applicable."
                    ),
                )
            )

        # CNTR-010: Resource limits defined (use docker-compose as a proxy signal)
        check = check_map["CNTR-010"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        elif data.has_docker_compose:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "A docker-compose file is present. "
                        "Confirm that CPU and memory resource limits are explicitly defined within it."
                    ),
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Resource limit definitions could not be verified automatically. "
                        "Confirm that CPU and memory limits are set in the deployment manifests or compose files."
                    ),
                )
            )

        # CNTR-011: Container signing enabled
        check = check_map["CNTR-011"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Container image signing could not be verified automatically. "
                        "Confirm that images are signed using Cosign, Notary, or an equivalent tool."
                    ),
                )
            )

        # CNTR-012: Runtime security policy defined
        check = check_map["CNTR-012"]
        if not has_dockerfile:
            results.append(
                CheckResult(check=check, status=CheckStatus.not_applicable, detail=_na_detail)
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.warning,
                    detail=(
                        "Runtime security policy configuration could not be verified automatically. "
                        "Confirm that seccomp profiles, AppArmor policies, or Pod Security Standards are applied."
                    ),
                )
            )

        return results
