from __future__ import annotations

# Domain models - imported in dependency order so Alembic autogenerate
# can discover every mapped class via Base.metadata.
from backend.models.agent_instructions import AgentInstructions
from backend.models.agent_runs import AgentRun, AgentStep, RemediationAction

# Import Base first so all subclasses register against the same metadata.
from backend.models.base import Base, TimestampMixin, UUIDMixin
from backend.models.customer import Customer, PlatformConnection

# Enums - no SQLAlchemy dependencies, import early.
from backend.models.enums import (
    AgentRunStatus,
    AgentStepType,
    AuthType,
    Category,
    CheckStatus,
    LLMProviderEnum,
    Platform,
    RemediationActionStatus,
    ReportStatus,
    ScanStatus,
    Severity,
)
from backend.models.finding import Finding, ScanScore
from backend.models.llm import LLMConnection
from backend.models.report import Report, ReportTemplate
from backend.models.requirement import CustomRequirement, RequirementResult
from backend.models.scan import Scan, ScanRepo
from backend.models.scan_profile import ScanProfile
from backend.models.skill import Skill, SkillToggle

__all__ = [
    # Base classes
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    # Enums
    "AgentRunStatus",
    "AgentStepType",
    "AuthType",
    "Category",
    "CheckStatus",
    "LLMProviderEnum",
    "Platform",
    "RemediationActionStatus",
    "ReportStatus",
    "ScanStatus",
    "Severity",
    # Models
    "AgentInstructions",
    "AgentRun",
    "AgentStep",
    "Customer",
    "CustomRequirement",
    "Finding",
    "LLMConnection",
    "PlatformConnection",
    "RemediationAction",
    "Report",
    "ReportTemplate",
    "RequirementResult",
    "Scan",
    "ScanProfile",
    "ScanRepo",
    "ScanScore",
    "Skill",
    "SkillToggle",
]
