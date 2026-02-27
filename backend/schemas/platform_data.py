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
# Organisation-level assessment models
# ---------------------------------------------------------------------------


class OrgMemberInfo(BaseModel):
    """Membership statistics for an organisation."""

    total_members: int = 0
    admin_count: int = 0
    mfa_enforced: bool = False
    sso_enabled: bool = False


class OrgSecuritySettings(BaseModel):
    """Organisation-level security configuration."""

    default_repo_permission: str | None = None
    members_can_create_public_repos: bool = True
    two_factor_requirement_enabled: bool = False
    ip_allow_list_enabled: bool = False


class OrgAssessmentData(BaseModel):
    """All data collected at the organisation level, ready for scoring.

    Used by org-level scanners (platform_arch, identity_access, etc.).
    """

    org_name: str
    members: OrgMemberInfo | None = None
    security_settings: OrgSecuritySettings | None = None
    has_org_level_security_policy: bool = False
    billing_plan: str | None = None


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
    # Expanded fields for 16-domain scanners
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    has_container_scanning: bool = False
    has_iac_files: bool = False
    has_monitoring_config: bool = False
    has_backup_config: bool = False
    has_changelog: bool = False
    has_adr_directory: bool = False
    has_sast_config: bool = False
    has_dast_config: bool = False
    has_api_docs: bool = False
    has_runbook: bool = False
    has_sla_document: bool = False
    has_migration_guide: bool = False
    has_deprecation_policy: bool = False
    has_issue_templates: bool = False
    has_discussions_enabled: bool = False
    has_project_boards: bool = False
    has_wiki: bool = False
    has_branching_strategy_doc: bool = False
    has_release_process_doc: bool = False
    has_hotfix_process_doc: bool = False
    has_definition_of_done: bool = False
    has_feature_flags: bool = False
    has_editorconfig: bool = False
    has_type_checking: bool = False
    has_dr_runbook: bool = False
    has_incident_response_playbook: bool = False
    has_on_call_doc: bool = False
    has_dashboards_as_code: bool = False
    container_base_images: list[str] = Field(default_factory=list)
    iac_tool: str | None = None
    test_coverage_percent: float | None = None
