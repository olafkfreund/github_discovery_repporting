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
    """Top-level finding / requirement categories (16 domains)."""

    platform_arch = "platform_arch"
    identity_access = "identity_access"
    repo_governance = "repo_governance"
    cicd = "cicd"
    secrets_mgmt = "secrets_mgmt"
    dependencies = "dependencies"
    sast = "sast"
    dast = "dast"
    container_security = "container_security"
    code_quality = "code_quality"
    sdlc_process = "sdlc_process"
    compliance = "compliance"
    collaboration = "collaboration"
    disaster_recovery = "disaster_recovery"
    monitoring = "monitoring"
    migration = "migration"


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


class LLMProviderEnum(str, Enum):
    """Supported LLM provider backends for per-customer AI configuration."""

    anthropic = "anthropic"
    openai = "openai"
    bedrock = "bedrock"
    azure_openai = "azure_openai"
    vertex = "vertex"
    openai_compatible = "openai_compatible"


class AgentRunStatus(str, Enum):
    """Lifecycle states for a remediation agent run."""

    pending = "pending"
    running = "running"
    opening_pr = "opening_pr"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentStepType(str, Enum):
    """Type of an individual step recorded during an agent run."""

    llm_call = "llm_call"
    tool_call = "tool_call"
    tool_result = "tool_result"
    observation = "observation"
    final = "final"


class RemediationActionStatus(str, Enum):
    """Lifecycle states for a pull-request remediation action."""

    planned = "planned"
    in_progress = "in_progress"
    opened = "opened"
    merged = "merged"
    closed = "closed"
    failed = "failed"
