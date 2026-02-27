from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.schemas.platform_data import (
    BranchProtection,
    CIWorkflow,
    NormalizedRepo,
    OrgAssessmentData,
    OrgMemberInfo,
    OrgSecuritySettings,
    PullRequestInfo,
    RepoAssessmentData,
    SecurityFeatures,
    WorkflowRun,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year: int, month: int, day: int) -> datetime:
    """Return a timezone-aware UTC datetime for the given date."""
    return datetime(year, month, day, tzinfo=UTC)


def _make_repo(
    name: str = "test-repo", url: str = "https://github.com/org/test-repo"
) -> NormalizedRepo:
    """Return a minimal :class:`NormalizedRepo` with sensible defaults."""
    return NormalizedRepo(
        external_id="1",
        name=name,
        url=url,
        default_branch="main",
        is_private=False,
        description="A repository used in scanner tests.",
        language="Python",
        created_at=_utc(2023, 1, 1),
        updated_at=_utc(2024, 6, 1),
        topics=["python", "testing"],
    )


def _make_success_run(duration_seconds: int = 240) -> WorkflowRun:
    """Return a completed successful :class:`WorkflowRun`."""
    return WorkflowRun(
        status="completed",
        conclusion="success",
        duration_seconds=duration_seconds,
        created_at=_utc(2024, 6, 1),
    )


def _make_failure_run() -> WorkflowRun:
    """Return a completed failed :class:`WorkflowRun`."""
    return WorkflowRun(
        status="completed",
        conclusion="failure",
        duration_seconds=300,
        created_at=_utc(2024, 6, 1),
    )


# ---------------------------------------------------------------------------
# Org-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def well_configured_org() -> OrgAssessmentData:
    """A fully hardened organisation with all security features enabled."""
    return OrgAssessmentData(
        org_name="test-org",
        members=OrgMemberInfo(
            total_members=100,
            admin_count=3,
            mfa_enforced=True,
            sso_enabled=True,
        ),
        security_settings=OrgSecuritySettings(
            default_repo_permission="read",
            members_can_create_public_repos=False,
            two_factor_requirement_enabled=True,
            ip_allow_list_enabled=True,
        ),
        has_org_level_security_policy=True,
        billing_plan="enterprise",
    )


@pytest.fixture()
def minimal_org() -> OrgAssessmentData:
    """An organisation with minimal configuration."""
    return OrgAssessmentData(
        org_name="minimal-org",
    )


# ---------------------------------------------------------------------------
# Repo-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def well_protected_repo() -> RepoAssessmentData:
    """A repository with all security, CI, and collaboration features enabled.

    Satisfies every non-warning check across all 16 scanner categories.
    """
    recent_runs = [_make_success_run(duration_seconds=240) for _ in range(20)]

    ci_workflow = CIWorkflow(
        name="CI",
        path=".github/workflows/ci.yml",
        trigger_events=["push", "pull_request"],
        has_tests=True,
        has_lint=True,
        has_security_scan=True,
        has_deploy=True,
        recent_runs=recent_runs,
    )

    branch_protection = BranchProtection(
        is_protected=True,
        required_reviews=2,
        dismiss_stale_reviews=True,
        require_code_owner_reviews=True,
        enforce_admins=True,
        allow_force_pushes=False,
        require_signed_commits=True,
    )

    security = SecurityFeatures(
        dependabot_enabled=True,
        secret_scanning_enabled=True,
        code_scanning_enabled=True,
        vulnerability_alerts=[],
        has_security_policy=True,
    )

    recent_prs = [
        PullRequestInfo(
            number=i,
            title=f"PR {i}",
            additions=50,
            deletions=30,
            review_count=2,
            merged=True,
            created_at=_utc(2024, 5, 1),
        )
        for i in range(1, 11)
    ]

    return RepoAssessmentData(
        repo=_make_repo(),
        branch_protection=branch_protection,
        ci_workflows=[ci_workflow],
        security=security,
        has_codeowners=True,
        has_pr_template=True,
        has_contributing_guide=True,
        has_license=True,
        has_readme=True,
        has_sbom=True,
        recent_prs=recent_prs,
        # Expanded fields
        has_dockerfile=True,
        has_docker_compose=True,
        has_container_scanning=True,
        has_iac_files=True,
        has_monitoring_config=True,
        has_backup_config=True,
        has_changelog=True,
        has_adr_directory=True,
        has_sast_config=True,
        has_dast_config=True,
        has_api_docs=True,
        has_runbook=True,
        has_sla_document=True,
        has_migration_guide=True,
        has_deprecation_policy=True,
        has_issue_templates=True,
        has_discussions_enabled=True,
        has_project_boards=True,
        has_wiki=True,
        has_branching_strategy_doc=True,
        has_release_process_doc=True,
        has_hotfix_process_doc=True,
        has_definition_of_done=True,
        has_feature_flags=True,
        has_editorconfig=True,
        has_type_checking=True,
        has_dr_runbook=True,
        has_incident_response_playbook=True,
        has_on_call_doc=True,
        has_dashboards_as_code=True,
        iac_tool="terraform",
        test_coverage_percent=85.0,
    )


@pytest.fixture()
def minimal_repo() -> RepoAssessmentData:
    """A repository with almost nothing configured.

    Only a :class:`NormalizedRepo` with a name and URL is present; every
    optional feature flag is absent or falsy.
    """
    return RepoAssessmentData(
        repo=_make_repo(name="minimal-repo", url="https://github.com/org/minimal-repo"),
    )


@pytest.fixture()
def partial_repo() -> RepoAssessmentData:
    """A repository with partial configuration.

    - Branch protection enabled with 1 required review.
    - No stale-review dismissal, no admin enforcement, no signed commits.
    - Security features present but only dependabot.
    - CI workflow present with tests only.
    - README and LICENSE present; some other files.
    - Recent PRs present but only some are reviewed.
    """
    ci_workflow = CIWorkflow(
        name="tests",
        path=".github/workflows/tests.yml",
        trigger_events=["push", "pull_request"],
        has_tests=True,
        has_lint=False,
        has_security_scan=False,
        has_deploy=False,
        recent_runs=[_make_success_run() for _ in range(10)],
    )

    branch_protection = BranchProtection(
        is_protected=True,
        required_reviews=1,
        dismiss_stale_reviews=False,
        require_code_owner_reviews=False,
        enforce_admins=False,
        allow_force_pushes=False,
        require_signed_commits=False,
    )

    security = SecurityFeatures(
        dependabot_enabled=True,
        secret_scanning_enabled=False,
        code_scanning_enabled=False,
        vulnerability_alerts=[],
        has_security_policy=False,
    )

    # 4 PRs reviewed out of 5 merged (80%)
    recent_prs = [
        PullRequestInfo(
            number=i,
            title=f"PR {i}",
            additions=100,
            deletions=40,
            review_count=1 if i < 5 else 0,
            merged=True,
            created_at=_utc(2024, 5, 1),
        )
        for i in range(1, 6)
    ]

    return RepoAssessmentData(
        repo=_make_repo(name="partial-repo", url="https://github.com/org/partial-repo"),
        branch_protection=branch_protection,
        ci_workflows=[ci_workflow],
        security=security,
        has_codeowners=False,
        has_pr_template=False,
        has_contributing_guide=False,
        has_license=True,
        has_readme=True,
        has_sbom=False,
        recent_prs=recent_prs,
        has_dockerfile=True,
        has_changelog=True,
        has_editorconfig=True,
    )
