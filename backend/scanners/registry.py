"""Scanner registry — auto-generates metadata from scanner code.

Provides a single source of truth for all categories, checks, and
configurable thresholds.  The ``get_scanner_registry()`` function
instantiates ``ScanOrchestrator``, iterates every scanner, and returns
structured metadata suitable for the API and frontend profile editor.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.models.enums import Category, Severity
from backend.scanners.base import ScanCheck

# ---------------------------------------------------------------------------
# Threshold defaults — maps check_id to key/default pairs.
# Only checks with user-tunable thresholds are listed here.
# ---------------------------------------------------------------------------

THRESHOLD_REGISTRY: dict[str, dict[str, float]] = {
    "CICD-008": {"pass_threshold": 0.95, "warning_threshold": 0.80},
    "CICD-009": {"max_seconds": 600},
    "IAM-003": {"max_admin_ratio": 0.05},
    "CQ-004": {"min_coverage_pct": 60.0},
    "SDLC-003": {"pass_threshold": 0.75, "warning_threshold": 0.50},
    "SDLC-004": {"pass_threshold": 500, "warning_threshold": 1000},
    "COLLAB-006": {"pass_threshold": 0.90, "warning_threshold": 0.75},
}


# ---------------------------------------------------------------------------
# Human-readable category display names.
# ---------------------------------------------------------------------------

CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "platform_arch": "Platform Architecture",
    "identity_access": "Identity & Access Management",
    "repo_governance": "Repository Governance",
    "cicd": "CI/CD Pipeline",
    "secrets_mgmt": "Secrets Management",
    "dependencies": "Dependency Management",
    "sast": "Static Application Security Testing",
    "dast": "Dynamic Application Security Testing",
    "container_security": "Container Security",
    "code_quality": "Code Quality",
    "sdlc_process": "SDLC Process",
    "compliance": "Compliance",
    "collaboration": "Collaboration",
    "disaster_recovery": "Disaster Recovery",
    "monitoring": "Monitoring & Observability",
    "migration": "Migration Readiness",
}


# ---------------------------------------------------------------------------
# Dataclasses returned by the registry API.
# ---------------------------------------------------------------------------


@dataclass
class ThresholdInfo:
    """A single configurable threshold on a check."""

    key: str
    default_value: float


@dataclass
class CheckInfo:
    """Metadata for a single scan check."""

    check_id: str
    check_name: str
    severity: str
    weight: float
    description: str
    thresholds: list[ThresholdInfo] = field(default_factory=list)


@dataclass
class CategoryInfo:
    """Metadata for a scanner category with its checks."""

    category: str
    display_name: str
    weight: float
    scope: str  # "org" or "repo"
    checks: list[CheckInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry builder.
# ---------------------------------------------------------------------------


def _build_check_info(check: ScanCheck) -> CheckInfo:
    """Convert a :class:`ScanCheck` into a :class:`CheckInfo` with threshold data."""
    thresholds: list[ThresholdInfo] = []
    if check.check_id in THRESHOLD_REGISTRY:
        for key, default in THRESHOLD_REGISTRY[check.check_id].items():
            thresholds.append(ThresholdInfo(key=key, default_value=default))

    return CheckInfo(
        check_id=check.check_id,
        check_name=check.check_name,
        severity=check.severity.value if isinstance(check.severity, Severity) else str(check.severity),
        weight=check.weight,
        description=check.description,
        thresholds=thresholds,
    )


def get_scanner_registry() -> list[CategoryInfo]:
    """Return structured metadata for all 16 scanner categories.

    This function instantiates a fresh :class:`ScanOrchestrator` and
    reflects over its scanners, so the registry is always in sync with
    the actual scanner code — nothing is manually maintained.
    """
    from backend.scanners.orchestrator import ScanOrchestrator  # noqa: PLC0415

    orchestrator = ScanOrchestrator()

    # Determine which scanners are org-level vs repo-level.
    org_categories: set[str] = set()
    for scanner in orchestrator._org_scanners:
        cat = scanner.category
        org_categories.add(cat.value if isinstance(cat, Category) else str(cat))

    categories: list[CategoryInfo] = []

    for s in orchestrator.all_scanners:
        cat = s.category
        cat_value = cat.value if isinstance(cat, Category) else str(cat)
        scope = "org" if cat_value in org_categories else "repo"
        display = CATEGORY_DISPLAY_NAMES.get(cat_value, cat_value.replace("_", " ").title())

        checks_info = [_build_check_info(c) for c in s.checks()]

        categories.append(
            CategoryInfo(
                category=cat_value,
                display_name=display,
                weight=s.weight,
                scope=scope,
                checks=checks_info,
            )
        )

    return categories


def registry_to_dicts(registry: list[CategoryInfo]) -> list[dict[str, Any]]:
    """Serialise a registry list to plain dicts for JSON responses."""
    return [asdict(cat) for cat in registry]
