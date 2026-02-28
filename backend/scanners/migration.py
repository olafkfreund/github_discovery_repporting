from __future__ import annotations

from backend.models.enums import Category, Severity
from backend.scanners.base import BaseScanner, CheckResult, ScanCheck
from backend.schemas.platform_data import RepoAssessmentData


class MigrationScanner(BaseScanner):
    """Evaluates migration readiness for a repository.

    Checks cover migration guides, API versioning, deprecation policies,
    database migration tooling, backwards compatibility, and environment
    parity practices.

    Category weight: 0.02.
    """

    category: Category = Category.migration
    weight: float = 0.02

    # ------------------------------------------------------------------
    # Check catalogue
    # ------------------------------------------------------------------

    _CHECKS = (
        ScanCheck(
            check_id="MIG-001",
            check_name="Migration guide present",
            category=Category.migration,
            severity=Severity.medium,
            weight=1.0,
            description="A migration guide must be present to assist consumers when upgrading between versions.",
        ),
        ScanCheck(
            check_id="MIG-002",
            check_name="API versioning implemented",
            category=Category.migration,
            severity=Severity.medium,
            weight=1.0,
            description="API versioning should be implemented and documented to support gradual migration.",
        ),
        ScanCheck(
            check_id="MIG-003",
            check_name="Deprecation policy documented",
            category=Category.migration,
            severity=Severity.medium,
            weight=1.0,
            description="A deprecation policy must be documented to communicate breaking-change timelines.",
        ),
        ScanCheck(
            check_id="MIG-004",
            check_name="Database migration tool configured",
            category=Category.migration,
            severity=Severity.medium,
            weight=1.0,
            description="A database migration tool (e.g. Alembic, Flyway, Liquibase) must be configured.",
        ),
        ScanCheck(
            check_id="MIG-005",
            check_name="Feature parity documentation",
            category=Category.migration,
            severity=Severity.low,
            weight=0.5,
            description="Feature parity documentation should describe equivalent capabilities between versions or platforms.",
        ),
        ScanCheck(
            check_id="MIG-006",
            check_name="Data export capability",
            category=Category.migration,
            severity=Severity.medium,
            weight=1.0,
            description="The system must provide data export capability to prevent vendor lock-in.",
        ),
        ScanCheck(
            check_id="MIG-007",
            check_name="Backwards compatibility testing",
            category=Category.migration,
            severity=Severity.medium,
            weight=1.0,
            description="Backwards compatibility tests must be present to catch breaking changes before release.",
        ),
        ScanCheck(
            check_id="MIG-008",
            check_name="Environment parity (dev/staging/prod)",
            category=Category.migration,
            severity=Severity.medium,
            weight=1.0,
            description="Development, staging, and production environments should maintain parity to reduce migration surprises.",
        ),
        ScanCheck(
            check_id="MIG-009",
            check_name="Platform abstraction layer present",
            category=Category.migration,
            severity=Severity.low,
            weight=0.5,
            description="A platform abstraction layer should be present to reduce coupling and ease future migrations.",
        ),
    )

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]:
        """Run every MIG-xxx check against *data* and return one result each."""
        results: list[CheckResult] = []

        # MIG-001 — Migration guide present
        results.append(
            self._bool_check(
                "MIG-001",
                data.has_migration_guide,
                passed="A migration guide is present in the repository.",
                failed="No migration guide was found.",
            )
        )

        # MIG-002 — API versioning implemented (proxied via API docs presence)
        results.append(
            self._bool_check(
                "MIG-002",
                data.has_api_docs,
                passed="API documentation is present, indicating API versioning is likely implemented.",
                failed="No API documentation found; API versioning may not be implemented.",
            )
        )

        # MIG-003 — Deprecation policy documented
        results.append(
            self._bool_check(
                "MIG-003",
                data.has_deprecation_policy,
                passed="A deprecation policy document is present in the repository.",
                failed="No deprecation policy document was found.",
            )
        )

        # MIG-004 — Database migration tool configured (not verifiable via standard API)
        results.append(self._manual_review("MIG-004", "Database migration tool configuration"))

        # MIG-005 — Feature parity documentation (not verifiable via standard API)
        results.append(self._manual_review("MIG-005", "Feature parity documentation"))

        # MIG-006 — Data export capability (not verifiable via standard API)
        results.append(self._manual_review("MIG-006", "Data export capability"))

        # MIG-007 — Backwards compatibility testing (not verifiable via standard API)
        results.append(self._manual_review("MIG-007", "Backwards compatibility test coverage"))

        # MIG-008 — Environment parity (not verifiable via standard API)
        results.append(self._manual_review("MIG-008", "Environment parity between development, staging, and production"))

        # MIG-009 — Platform abstraction layer present (not verifiable via standard API)
        results.append(self._manual_review("MIG-009", "The presence of a platform abstraction layer"))

        return results
