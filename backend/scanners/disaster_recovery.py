from __future__ import annotations

from backend.models.enums import Category, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData


class DisasterRecoveryScanner(BaseScanner):
    """Evaluates repository-level disaster recovery preparedness.

    Checks cover backup strategy, runbooks, RTO/RPO documentation,
    Infrastructure as Code presence, and failover procedures.

    Category weight: 0.04.
    """

    category: Category = Category.disaster_recovery
    weight: float = 0.04

    # ------------------------------------------------------------------
    # Check catalogue
    # ------------------------------------------------------------------

    _CHECKS = (
        ScanCheck(
            check_id="DR-001",
            check_name="Backup strategy documented",
            category=Category.disaster_recovery,
            severity=Severity.high,
            weight=1.5,
            description="A backup configuration or strategy document must be present in the repository.",
        ),
        ScanCheck(
            check_id="DR-002",
            check_name="Repository mirroring configured",
            category=Category.disaster_recovery,
            severity=Severity.medium,
            weight=1.0,
            description="Repository mirroring should be configured to ensure geo-redundant source code availability.",
        ),
        ScanCheck(
            check_id="DR-003",
            check_name="DR runbook present",
            category=Category.disaster_recovery,
            severity=Severity.high,
            weight=1.5,
            description="A disaster recovery runbook must be present describing steps to restore the system.",
        ),
        ScanCheck(
            check_id="DR-004",
            check_name="Recovery time objective defined",
            category=Category.disaster_recovery,
            severity=Severity.medium,
            weight=1.0,
            description="The recovery time objective (RTO) must be documented, typically in an SLA or SLO document.",
        ),
        ScanCheck(
            check_id="DR-005",
            check_name="Recovery point objective defined",
            category=Category.disaster_recovery,
            severity=Severity.medium,
            weight=1.0,
            description="The recovery point objective (RPO) must be documented, typically in an SLA or SLO document.",
        ),
        ScanCheck(
            check_id="DR-006",
            check_name="Backup testing schedule documented",
            category=Category.disaster_recovery,
            severity=Severity.medium,
            weight=1.0,
            description="A schedule for regularly testing backups must be documented to verify recoverability.",
        ),
        ScanCheck(
            check_id="DR-007",
            check_name="Infrastructure as Code present",
            category=Category.disaster_recovery,
            severity=Severity.high,
            weight=1.5,
            description="Infrastructure must be defined as code (Terraform, Pulumi, etc.) to enable repeatable recovery.",
        ),
        ScanCheck(
            check_id="DR-008",
            check_name="Multi-region deployment capable",
            category=Category.disaster_recovery,
            severity=Severity.medium,
            weight=1.0,
            description="Deployment configuration should support multi-region operation for high availability.",
        ),
        ScanCheck(
            check_id="DR-009",
            check_name="Failover procedure documented",
            category=Category.disaster_recovery,
            severity=Severity.medium,
            weight=1.0,
            description="A documented failover procedure must be available for operators during an outage.",
        ),
        ScanCheck(
            check_id="DR-010",
            check_name="Data restoration tested",
            category=Category.disaster_recovery,
            severity=Severity.low,
            weight=0.5,
            description="Evidence of successful data restoration tests should be recorded or referenced.",
        ),
    )

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every DR-xxx check against *data* and return one result each."""
        results: list[CheckResult] = []

        # DR-001 — Backup strategy documented
        results.append(
            self._bool_check(
                "DR-001",
                data.has_backup_config,
                passed="Backup configuration file detected in the repository.",
                failed="No backup configuration or strategy document was found.",
            )
        )

        # DR-002 — Repository mirroring configured (not verifiable via standard API)
        results.append(self._manual_review("DR-002", "Repository mirroring configuration"))

        # DR-003 — DR runbook present
        results.append(
            self._bool_check(
                "DR-003",
                data.has_dr_runbook,
                passed="A disaster recovery runbook is present in the repository.",
                failed="No disaster recovery runbook was found.",
            )
        )

        # DR-004 — Recovery time objective defined (proxied via SLA document)
        results.append(
            self._bool_check(
                "DR-004",
                data.has_sla_document,
                passed="An SLA/SLO document is present, which should define the RTO.",
                failed="No SLA/SLO document found; recovery time objective (RTO) may be undefined.",
            )
        )

        # DR-005 — Recovery point objective defined (proxied via SLA document)
        results.append(
            self._bool_check(
                "DR-005",
                data.has_sla_document,
                passed="An SLA/SLO document is present, which should define the RPO.",
                failed="No SLA/SLO document found; recovery point objective (RPO) may be undefined.",
            )
        )

        # DR-006 — Backup testing schedule documented (not verifiable via standard API)
        results.append(self._manual_review("DR-006", "Backup testing schedule documentation"))

        # DR-007 — Infrastructure as Code present
        results.append(
            self._bool_check(
                "DR-007",
                data.has_iac_files,
                passed="Infrastructure as Code files detected, enabling repeatable environment recovery.",
                failed="No Infrastructure as Code files detected; environment recovery may require manual steps.",
                evidence={"iac_tool": data.iac_tool} if data.iac_tool else None,
            )
        )

        # DR-008 — Multi-region deployment capable (not verifiable via standard API)
        results.append(self._manual_review("DR-008", "Multi-region deployment capability"))

        # DR-009 — Failover procedure documented (not verifiable via standard API)
        results.append(self._manual_review("DR-009", "Failover procedure documentation"))

        # DR-010 — Data restoration tested (not verifiable via standard API)
        results.append(self._manual_review("DR-010", "Evidence of data restoration testing"))

        return results
