from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Primitive / leaf models
# ---------------------------------------------------------------------------


class WorkflowRun(BaseModel):
    """A single execution record for a CI workflow."""

    status: str
    conclusion: str | None = None
    duration_seconds: int | None = None
    created_at: datetime | None = None


class VulnerabilityAlert(BaseModel):
    """A single dependency or code vulnerability surfaced by the platform."""

    severity: str
    package: str
    title: str
    state: str


class PullRequestInfo(BaseModel):
    """Summary metadata for a pull request, used for PR-cadence analysis."""

    number: int
    title: str
    additions: int
    deletions: int
    review_count: int
    merged: bool
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Composite / aggregate models
# ---------------------------------------------------------------------------


class NormalizedRepo(BaseModel):
    """Platform-agnostic representation of a source repository."""

    external_id: str
    name: str
    url: str
    default_branch: str
    is_private: bool
    description: str | None = None
    language: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    topics: list[str] = Field(default_factory=list)


class BranchProtection(BaseModel):
    """Branch protection rules as reported by the platform provider."""

    is_protected: bool
    required_reviews: int
    dismiss_stale_reviews: bool
    require_code_owner_reviews: bool
    enforce_admins: bool
    allow_force_pushes: bool
    require_signed_commits: bool


class CIWorkflow(BaseModel):
    """A CI/CD workflow definition discovered in the repository."""

    name: str
    path: str
    trigger_events: list[str]
    has_tests: bool = False
    has_lint: bool = False
    has_security_scan: bool = False
    has_deploy: bool = False
    recent_runs: list[WorkflowRun] = Field(default_factory=list)


class SecurityFeatures(BaseModel):
    """Security tooling and alert data for a repository."""

    dependabot_enabled: bool = False
    secret_scanning_enabled: bool = False
    code_scanning_enabled: bool = False
    vulnerability_alerts: list[VulnerabilityAlert] = Field(default_factory=list)
    has_security_policy: bool = False


# ---------------------------------------------------------------------------
# Top-level assessment payload
# ---------------------------------------------------------------------------


class RepoAssessmentData(BaseModel):
    """All data collected for a single repository, ready for scoring.

    This model is used internally by the scanning and analysis pipeline;
    it is never persisted directly to the database.
    """

    repo: NormalizedRepo
    branch_protection: BranchProtection | None = None
    ci_workflows: list[CIWorkflow] = Field(default_factory=list)
    security: SecurityFeatures | None = None
    has_codeowners: bool = False
    has_pr_template: bool = False
    has_contributing_guide: bool = False
    has_license: bool = False
    has_readme: bool = False
    has_sbom: bool = False
    recent_prs: list[PullRequestInfo] = Field(default_factory=list)
