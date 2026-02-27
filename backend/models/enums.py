from __future__ import annotations

from enum import Enum


class Platform(str, Enum):
    """Supported source control and DevOps platforms."""

    github = "github"
    gitlab = "gitlab"
    azure_devops = "azure_devops"


class AuthType(str, Enum):
    """Authentication mechanism used for a platform connection."""

    token = "token"
    oauth = "oauth"
    pat = "pat"


class ScanStatus(str, Enum):
    """Lifecycle states for a repository scan."""

    pending = "pending"
    scanning = "scanning"
    analyzing = "analyzing"
    generating_report = "generating_report"
    completed = "completed"
    failed = "failed"


class Category(str, Enum):
    """Top-level finding / requirement categories."""

    security = "security"
    cicd = "cicd"
    code_quality = "code_quality"
    collaboration = "collaboration"
    governance = "governance"


class Severity(str, Enum):
    """Finding severity levels, ordered from most to least severe."""

    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class CheckStatus(str, Enum):
    """Outcome of an individual check or requirement evaluation."""

    passed = "passed"
    failed = "failed"
    warning = "warning"
    not_applicable = "not_applicable"
    error = "error"


class ReportStatus(str, Enum):
    """Lifecycle states for a generated report."""

    pending = "pending"
    generating = "generating"
    completed = "completed"
    failed = "failed"
