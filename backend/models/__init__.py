from __future__ import annotations

# Import Base first so all subclasses register against the same metadata.
from backend.models.base import Base, TimestampMixin, UUIDMixin

# Domain models - imported in dependency order so Alembic autogenerate
# can discover every mapped class via Base.metadata.
from backend.models.customer import Customer, PlatformConnection

# Enums - no SQLAlchemy dependencies, import early.
from backend.models.enums import (
    AuthType,
    Category,
    CheckStatus,
    Platform,
    ReportStatus,
    ScanStatus,
    Severity,
)
from backend.models.finding import Finding, ScanScore
from backend.models.report import Report, ReportTemplate
from backend.models.requirement import CustomRequirement, RequirementResult
from backend.models.scan import Scan, ScanRepo

__all__ = [
    # Base classes
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    # Enums
    "AuthType",
    "Category",
    "CheckStatus",
    "Platform",
    "ReportStatus",
    "ScanStatus",
    "Severity",
    # Models
    "Customer",
    "CustomRequirement",
    "Finding",
    "PlatformConnection",
    "Report",
    "ReportTemplate",
    "RequirementResult",
    "Scan",
    "ScanRepo",
    "ScanScore",
]
