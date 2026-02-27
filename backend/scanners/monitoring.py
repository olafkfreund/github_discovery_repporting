from __future__ import annotations

from backend.models.enums import Category, CheckStatus, Severity
from backend.scanners.base import CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData


class MonitoringScanner:
    """Evaluates monitoring and observability maturity for a repository.

    Checks cover monitoring configuration, alerting, logging, tracing,
    health checks, SLO documentation, on-call processes, and incident
    response readiness.

    Category weight: 0.04.
    """

    category: Category = Category.monitoring
    weight: float = 0.04

    # ------------------------------------------------------------------
    # Check catalogue
    # ------------------------------------------------------------------

    _CHECKS: list[ScanCheck] = [
        ScanCheck(
            check_id="MON-001",
            check_name="Monitoring configuration present",
            category=Category.monitoring,
            severity=Severity.high,
            weight=1.5,
            description="A monitoring configuration file (e.g. Prometheus, Datadog, CloudWatch) must be present.",
        ),
        ScanCheck(
            check_id="MON-002",
            check_name="Alerting rules defined",
            category=Category.monitoring,
            severity=Severity.high,
            weight=1.5,
            description="Alerting rules must be defined to notify operators of production issues.",
        ),
        ScanCheck(
            check_id="MON-003",
            check_name="Logging framework configured",
            category=Category.monitoring,
            severity=Severity.medium,
            weight=1.0,
            description="A structured logging framework must be configured and documented.",
        ),
        ScanCheck(
            check_id="MON-004",
            check_name="Distributed tracing enabled",
            category=Category.monitoring,
            severity=Severity.medium,
            weight=1.0,
            description="Distributed tracing (e.g. OpenTelemetry, Jaeger, Zipkin) should be enabled for request tracking.",
        ),
        ScanCheck(
            check_id="MON-005",
            check_name="Health check endpoints defined",
            category=Category.monitoring,
            severity=Severity.medium,
            weight=1.0,
            description="Health check endpoints must be defined to enable liveness and readiness probing.",
        ),
        ScanCheck(
            check_id="MON-006",
            check_name="SLO/SLA documentation present",
            category=Category.monitoring,
            severity=Severity.medium,
            weight=1.0,
            description="Service Level Objectives or Service Level Agreements must be documented.",
        ),
        ScanCheck(
            check_id="MON-007",
            check_name="Error tracking tool integrated",
            category=Category.monitoring,
            severity=Severity.medium,
            weight=1.0,
            description="An error tracking tool (e.g. Sentry, Rollbar, Bugsnag) should be integrated.",
        ),
        ScanCheck(
            check_id="MON-008",
            check_name="Performance benchmarks defined",
            category=Category.monitoring,
            severity=Severity.low,
            weight=0.5,
            description="Performance benchmarks or baseline metrics should be defined and tracked.",
        ),
        ScanCheck(
            check_id="MON-009",
            check_name="Dashboards as code present",
            category=Category.monitoring,
            severity=Severity.low,
            weight=0.5,
            description="Monitoring dashboards should be defined as code (e.g. Grafana JSON, Terraform) for reproducibility.",
        ),
        ScanCheck(
            check_id="MON-010",
            check_name="On-call rotation documented",
            category=Category.monitoring,
            severity=Severity.medium,
            weight=1.0,
            description="An on-call rotation schedule or policy must be documented for operational coverage.",
        ),
        ScanCheck(
            check_id="MON-011",
            check_name="Incident response playbook present",
            category=Category.monitoring,
            severity=Severity.high,
            weight=1.5,
            description="An incident response playbook must be present to guide operators during production incidents.",
        ),
    ]

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def checks(self) -> list[ScanCheck]:
        """Return the full catalogue of monitoring and observability checks."""
        return list(self._CHECKS)

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every MON-xxx check against *data* and return one result each."""
        check_map = {c.check_id: c for c in self._CHECKS}
        results: list[CheckResult] = []

        # MON-001 — Monitoring configuration present
        check = check_map["MON-001"]
        if data.has_monitoring_config:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A monitoring configuration file is present in the repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No monitoring configuration file was detected.",
                )
            )

        # MON-002 — Alerting rules defined (subset of monitoring; not separately detectable)
        check = check_map["MON-002"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Alerting rule definitions cannot be verified separately from general monitoring "
                    "configuration via the repository API. Manual review recommended."
                ),
            )
        )

        # MON-003 — Logging framework configured (not verifiable via standard API)
        check = check_map["MON-003"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Logging framework configuration cannot be determined automatically from repository "
                    "metadata. Manual review of application code and configuration is recommended."
                ),
            )
        )

        # MON-004 — Distributed tracing enabled (not verifiable via standard API)
        check = check_map["MON-004"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Distributed tracing enablement cannot be verified automatically via the repository "
                    "API. Manual review of application instrumentation is recommended."
                ),
            )
        )

        # MON-005 — Health check endpoints defined (proxied via runbook presence)
        check = check_map["MON-005"]
        if data.has_runbook:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="A runbook is present, which typically documents health check endpoints.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No runbook found; health check endpoint documentation may be absent.",
                )
            )

        # MON-006 — SLO/SLA documentation present
        check = check_map["MON-006"]
        if data.has_sla_document:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="An SLA/SLO document is present in the repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No SLA or SLO document was found.",
                )
            )

        # MON-007 — Error tracking tool integrated (not verifiable via standard API)
        check = check_map["MON-007"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Error tracking tool integration cannot be verified automatically from repository "
                    "metadata. Manual review of application dependencies and configuration is recommended."
                ),
            )
        )

        # MON-008 — Performance benchmarks defined (not verifiable via standard API)
        check = check_map["MON-008"]
        results.append(
            CheckResult(
                check=check,
                status=CheckStatus.warning,
                detail=(
                    "Performance benchmark definitions cannot be verified automatically. "
                    "Manual review of test suites and documentation is recommended."
                ),
            )
        )

        # MON-009 — Dashboards as code present
        check = check_map["MON-009"]
        if data.has_dashboards_as_code:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="Dashboard-as-code files detected in the repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No dashboard-as-code files were detected.",
                )
            )

        # MON-010 — On-call rotation documented
        check = check_map["MON-010"]
        if data.has_on_call_doc:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="An on-call rotation document is present in the repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No on-call rotation document was found.",
                )
            )

        # MON-011 — Incident response playbook present
        check = check_map["MON-011"]
        if data.has_incident_response_playbook:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.passed,
                    detail="An incident response playbook is present in the repository.",
                )
            )
        else:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.failed,
                    detail="No incident response playbook was found.",
                )
            )

        return results
