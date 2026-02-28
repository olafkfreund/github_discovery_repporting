from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from functools import partial
from typing import Any

import gitlab
import yaml
from gitlab.exceptions import GitlabError

from backend.models.enums import Platform
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
)

logger = logging.getLogger(__name__)

# Keywords used to classify CI job intent from name / content.
_TEST_KEYWORDS = frozenset({"test", "tests", "testing", "pytest", "jest", "rspec"})
_LINT_KEYWORDS = frozenset({"lint", "linting", "flake8", "eslint", "ruff", "rubocop"})
_SECURITY_KEYWORDS = frozenset(
    {"security", "codeql", "trivy", "snyk", "bandit", "semgrep", "gitleaks", "sast", "dast"}
)
_DEPLOY_KEYWORDS = frozenset({"deploy", "release", "publish", "ship", "cd"})


class GitLabProvider:
    """GitLab implementation of the PlatformProvider protocol.

    Uses the python-gitlab library. All blocking calls are offloaded to
    a thread-pool executor to avoid stalling the async event loop.

    Args:
        token: A GitLab personal access token or group access token.
        group: The GitLab group (or sub-group) path whose projects will be
            enumerated.
        base_url: Optional GitLab self-managed instance URL. Defaults to
            ``https://gitlab.com``.
    """

    platform: Platform = Platform.gitlab

    def __init__(
        self,
        token: str,
        group: str,
        base_url: str | None = None,
    ) -> None:
        self._token = token
        self._group = group
        self._base_url = base_url or "https://gitlab.com"
        self._client = gitlab.Gitlab(
            url=self._base_url,
            private_token=token,
        )

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous callable in the default thread-pool executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def _resolve_group(self) -> Any:
        """Resolve the configured group, trying direct lookup first then search.

        ``python-gitlab``'s ``groups.get()`` expects either a numeric ID or
        the **exact**, URL-encoded full path.  Users often enter just the
        display name, a differently-cased variant, or omit a parent path.

        Strategy:
        1. Try ``groups.get(self._group)`` (direct by path or ID).
        2. If 404, search for the group name and match case-insensitively.
        """
        try:
            return self._client.groups.get(self._group)
        except GitlabError:
            pass

        # Fallback: search and match
        try:
            results = self._client.groups.list(search=self._group, all=True)
            for g in results:
                path = getattr(g, "full_path", "") or ""
                name = getattr(g, "name", "") or ""
                if (
                    path.lower() == self._group.lower()
                    or name.lower() == self._group.lower()
                ):
                    logger.info(
                        "Resolved group %r via search → full_path=%r (id=%s)",
                        self._group,
                        path,
                        g.id,
                    )
                    self._group = path  # pin to canonical path for future calls
                    return self._client.groups.get(g.id)
        except GitlabError as exc:
            logger.debug("Group search fallback failed for %r: %s", self._group, exc)

        # Nothing found — raise a clear error
        raise GitlabError(f"404: Group '{self._group}' not found")

    async def validate_connection(self) -> bool:
        """Test that the token can reach the target group.

        Returns ``True`` on success.  Raises on failure so that callers
        can inspect the error message (e.g. the validate endpoint).
        """

        def _validate() -> bool:
            self._client.auth()
            self._resolve_group()
            return True

        return await self._run(_validate)

    async def list_repos(self) -> list[NormalizedRepo]:
        """Enumerate all projects in the configured group."""

        def _fetch() -> list[NormalizedRepo]:
            group = self._resolve_group()
            projects = group.projects.list(
                include_subgroups=True,
                all=True,
                with_shared=False,
            )
            results: list[NormalizedRepo] = []
            for p in projects:
                # Group project listings are lightweight; get full project for details
                full_project = self._client.projects.get(p.id)
                results.append(_normalize_project(full_project))
            return results

        return await self._run(_fetch)

    async def get_repo_assessment_data(
        self,
        repo: NormalizedRepo,
    ) -> RepoAssessmentData:
        """Collect all assessment data for a single project."""

        def _fetch_all() -> RepoAssessmentData:
            project = self._client.projects.get(repo.external_id)
            branch_protection = _fetch_branch_protection(project, repo.default_branch)
            ci_workflows = _fetch_ci_config(project)
            security = _fetch_security_features(project)
            file_flags = _fetch_file_flags(project)
            recent_prs = _fetch_recent_mrs(project)

            return RepoAssessmentData(
                repo=repo,
                branch_protection=branch_protection,
                ci_workflows=ci_workflows,
                security=security,
                recent_prs=recent_prs,
                **file_flags,
            )

        return await self._run(_fetch_all)

    async def get_org_assessment_data(self) -> OrgAssessmentData:
        """Collect group-level assessment data from GitLab."""

        def _fetch_group() -> OrgAssessmentData:
            group = self._resolve_group()

            # Membership stats
            members = OrgMemberInfo(total_members=0, admin_count=0)
            try:
                all_members = group.members.list(all=True)
                members.total_members = len(all_members)
                # GitLab access levels: 50 = Owner, 40 = Maintainer
                members.admin_count = sum(
                    1 for m in all_members if m.access_level >= 40
                )
            except GitlabError as exc:
                logger.debug("Could not fetch member counts for %s: %s", self._group, exc)

            # GitLab enforces 2FA at instance level, not group level typically
            # Check if group has any 2FA-related settings
            try:
                members.mfa_enforced = bool(getattr(group, "require_two_factor_authentication", False))
            except (GitlabError, AttributeError):
                pass

            # Security settings
            security_settings = OrgSecuritySettings()
            try:
                security_settings.default_repo_permission = getattr(
                    group, "default_branch_protection", None
                )
                # GitLab groups can restrict project creation visibility
                visibility = getattr(group, "visibility", "private")
                security_settings.members_can_create_public_repos = visibility == "public"
                security_settings.two_factor_requirement_enabled = bool(
                    getattr(group, "require_two_factor_authentication", False)
                )
            except (GitlabError, AttributeError) as exc:
                logger.debug(
                    "Could not fetch group security settings for %s: %s", self._group, exc
                )

            # Security policy — check for SECURITY.md in group
            has_security_policy = False
            try:
                projects = group.projects.list(search="security", per_page=5)
                for p in projects:
                    try:
                        full_p = self._client.projects.get(p.id)
                        full_p.files.get(file_path="SECURITY.md", ref=full_p.default_branch)
                        has_security_policy = True
                        break
                    except GitlabError:
                        continue
            except GitlabError:
                pass

            # Plan info
            billing_plan: str | None = None
            try:
                billing_plan = getattr(group, "plan", None)
            except (GitlabError, AttributeError):
                pass

            return OrgAssessmentData(
                org_name=self._group,
                members=members,
                security_settings=security_settings,
                has_org_level_security_policy=has_security_policy,
                billing_plan=billing_plan,
            )

        return await self._run(_fetch_group)


# ---------------------------------------------------------------------------
# Private synchronous helpers
# ---------------------------------------------------------------------------


def _normalize_project(project: Any) -> NormalizedRepo:
    """Convert a python-gitlab Project object to a NormalizedRepo."""
    return NormalizedRepo(
        external_id=str(project.id),
        name=project.path_with_namespace.split("/")[-1] if "/" in project.path_with_namespace else project.path_with_namespace,
        url=project.web_url,
        default_branch=getattr(project, "default_branch", None) or "main",
        is_private=project.visibility == "private",
        description=getattr(project, "description", None),
        language=None,  # GitLab requires a separate languages() call
        created_at=_parse_datetime(getattr(project, "created_at", None)),
        updated_at=_parse_datetime(getattr(project, "last_activity_at", None)),
        topics=list(getattr(project, "topics", []) or []),
    )


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string from GitLab."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, AttributeError):
        return None


def _fetch_branch_protection(project: Any, default_branch: str) -> BranchProtection | None:
    """Retrieve branch protection settings for the default branch."""
    try:
        branch = project.branches.get(default_branch)
        is_protected = branch.protected

        if not is_protected:
            return BranchProtection(
                is_protected=False,
                required_reviews=0,
                dismiss_stale_reviews=False,
                require_code_owner_reviews=False,
                enforce_admins=False,
                allow_force_pushes=False,
                require_signed_commits=False,
            )

        # Get detailed protection rules
        required_reviews = 0
        enforce_admins = False
        allow_force_pushes = False
        require_code_owner = False

        try:
            protection_rules = project.protectedbranches.get(default_branch)
            # GitLab push_access_levels
            push_levels = getattr(protection_rules, "push_access_levels", [])

            # If only maintainers can push, that's enforcement
            if push_levels:
                # access_level 40 = Maintainer, 30 = Developer
                min_push_level = min(
                    (lvl.get("access_level", 0) for lvl in push_levels if isinstance(lvl, dict)),
                    default=0,
                )
                enforce_admins = min_push_level >= 40

            # Force push allowed?
            allow_force_pushes = bool(getattr(protection_rules, "allow_force_push", False))

            # Code owners
            require_code_owner = bool(getattr(protection_rules, "code_owner_approval_required", False))
        except GitlabError as exc:
            logger.debug("Could not fetch protection details for %s: %s", project.path_with_namespace, exc)

        # Check approval rules for required reviews count
        try:
            approval_rules = project.approvalrules.list()
            if approval_rules:
                required_reviews = max(
                    (getattr(rule, "approvals_required", 0) for rule in approval_rules),
                    default=0,
                )
            else:
                # Fall back to project-level approval settings
                approvals = project.approvals.get()
                required_reviews = getattr(approvals, "approvals_before_merge", 0)
        except GitlabError:
            pass

        return BranchProtection(
            is_protected=True,
            required_reviews=required_reviews,
            dismiss_stale_reviews=False,  # GitLab handles this differently (reset approvals on push)
            require_code_owner_reviews=require_code_owner,
            enforce_admins=enforce_admins,
            allow_force_pushes=allow_force_pushes,
            require_signed_commits=False,  # GitLab doesn't enforce this at branch level
        )
    except GitlabError as exc:
        logger.debug(
            "Could not fetch branch protection for %s/%s: %s",
            project.path_with_namespace,
            default_branch,
            exc,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Unexpected error fetching branch protection for %s: %s",
            project.path_with_namespace,
            exc,
        )
        return None


def _fetch_ci_config(project: Any) -> list[CIWorkflow]:
    """Discover CI/CD configuration from .gitlab-ci.yml."""
    workflows: list[CIWorkflow] = []
    try:
        ci_file = project.files.get(file_path=".gitlab-ci.yml", ref=project.default_branch)
        raw_yaml = ci_file.decode().decode("utf-8")
        ci_data: dict[str, Any] = yaml.safe_load(raw_yaml) or {}
    except GitlabError:
        return workflows
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not parse .gitlab-ci.yml for %s: %s", project.path_with_namespace, exc)
        return workflows

    # GitLab CI has stages and jobs at the top level
    # Each job (non-keyword key) becomes a CIWorkflow
    reserved_keys = frozenset({
        "stages", "variables", "image", "services", "before_script",
        "after_script", "cache", "include", "default", "workflow", "pages",
    })

    full_text = raw_yaml.lower()

    for key, value in ci_data.items():
        if key.startswith(".") or key in reserved_keys:
            continue
        if not isinstance(value, dict):
            continue

        job_name = key
        name_lower = job_name.lower()
        job_text = (name_lower + " " + str(value)).lower()

        has_tests = bool(_TEST_KEYWORDS & set(job_text.split()))
        has_lint = bool(_LINT_KEYWORDS & set(job_text.split()))
        has_security = bool(_SECURITY_KEYWORDS & set(job_text.split()))
        has_deploy = bool(_DEPLOY_KEYWORDS & set(job_text.split()))

        # Determine trigger events from job rules/only
        trigger_events: list[str] = []
        only = value.get("only", [])
        if isinstance(only, list):
            trigger_events = [str(e) for e in only]
        rules = value.get("rules", [])
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict) and "if" in rule:
                    trigger_events.append(str(rule["if"]))

        workflows.append(
            CIWorkflow(
                name=job_name,
                path=".gitlab-ci.yml",
                trigger_events=trigger_events or ["push"],
                has_tests=has_tests,
                has_lint=has_lint,
                has_security_scan=has_security,
                has_deploy=has_deploy,
                recent_runs=[],
            )
        )

    # If no individual jobs parsed but CI file exists, report it as a single workflow
    if not workflows and ci_data:
        has_tests = bool(_TEST_KEYWORDS & set(full_text.split()))
        has_lint = bool(_LINT_KEYWORDS & set(full_text.split()))
        has_security = bool(_SECURITY_KEYWORDS & set(full_text.split()))
        has_deploy = bool(_DEPLOY_KEYWORDS & set(full_text.split()))
        workflows.append(
            CIWorkflow(
                name=".gitlab-ci.yml",
                path=".gitlab-ci.yml",
                trigger_events=["push"],
                has_tests=has_tests,
                has_lint=has_lint,
                has_security_scan=has_security,
                has_deploy=has_deploy,
                recent_runs=[],
            )
        )

    return workflows


def _fetch_security_features(project: Any) -> SecurityFeatures:
    """Probe security feature states for the project."""
    dependabot = False
    secret_scanning = False
    code_scanning = False
    has_security_policy = False

    # Security policy
    for path in ("SECURITY.md", ".gitlab/SECURITY.md", "docs/SECURITY.md"):
        try:
            project.files.get(file_path=path, ref=project.default_branch)
            has_security_policy = True
            break
        except GitlabError:
            continue

    # Dependabot equivalent — check for renovate or dependency scanning
    for path in ("renovate.json", ".renovaterc", ".renovaterc.json", ".gitlab/dependabot.yml"):
        try:
            project.files.get(file_path=path, ref=project.default_branch)
            dependabot = True
            break
        except GitlabError:
            continue

    # GitLab SAST / secret detection — check CI config for includes
    try:
        ci_file = project.files.get(file_path=".gitlab-ci.yml", ref=project.default_branch)
        ci_content = ci_file.decode().decode("utf-8").lower()
        if "sast" in ci_content or "code_quality" in ci_content or "semgrep" in ci_content:
            code_scanning = True
        if "secret" in ci_content and ("detection" in ci_content or "scanning" in ci_content):
            secret_scanning = True
    except GitlabError:
        pass

    return SecurityFeatures(
        dependabot_enabled=dependabot,
        secret_scanning_enabled=secret_scanning,
        code_scanning_enabled=code_scanning,
        vulnerability_alerts=[],
        has_security_policy=has_security_policy,
    )


def _fetch_file_flags(project: Any) -> dict[str, bool]:
    """Check for the presence of key repository files."""
    flags: dict[str, bool] = {
        "has_codeowners": False,
        "has_pr_template": False,
        "has_contributing_guide": False,
        "has_license": False,
        "has_readme": False,
        "has_sbom": False,
        "has_dockerfile": False,
        "has_docker_compose": False,
        "has_container_scanning": False,
        "has_iac_files": False,
        "has_monitoring_config": False,
        "has_backup_config": False,
        "has_changelog": False,
        "has_adr_directory": False,
        "has_sast_config": False,
        "has_dast_config": False,
        "has_api_docs": False,
        "has_runbook": False,
        "has_sla_document": False,
        "has_migration_guide": False,
        "has_deprecation_policy": False,
        "has_issue_templates": False,
        "has_discussions_enabled": False,
        "has_project_boards": False,
        "has_wiki": False,
        "has_branching_strategy_doc": False,
        "has_release_process_doc": False,
        "has_hotfix_process_doc": False,
        "has_definition_of_done": False,
        "has_feature_flags": False,
        "has_editorconfig": False,
        "has_type_checking": False,
        "has_dr_runbook": False,
        "has_incident_response_playbook": False,
        "has_on_call_doc": False,
        "has_dashboards_as_code": False,
    }

    candidate_paths: dict[str, list[str]] = {
        "has_codeowners": ["CODEOWNERS", ".gitlab/CODEOWNERS", "docs/CODEOWNERS"],
        "has_pr_template": [
            ".gitlab/merge_request_templates/default.md",
            ".gitlab/merge_request_templates/Default.md",
        ],
        "has_contributing_guide": ["CONTRIBUTING.md", ".gitlab/CONTRIBUTING.md", "docs/CONTRIBUTING.md"],
        "has_license": ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "LICENCE.md"],
        "has_readme": ["README.md", "README.rst", "README.txt", "README"],
        "has_sbom": ["sbom.json", "sbom.spdx", "sbom.cyclonedx.json", "bom.json", "bom.xml"],
        "has_dockerfile": ["Dockerfile", "dockerfile", "docker/Dockerfile"],
        "has_docker_compose": ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"],
        "has_container_scanning": [".trivy.yaml", ".grype.yaml"],
        "has_iac_files": ["main.tf", "terraform/main.tf", "Pulumi.yaml", "pulumi/Pulumi.yaml", "infrastructure/main.tf"],
        "has_monitoring_config": ["prometheus.yml", "monitoring/prometheus.yml", "datadog.yaml", ".datadog-ci.json"],
        "has_backup_config": ["backup.yml", "backup.yaml", "docs/backup-strategy.md"],
        "has_changelog": ["CHANGELOG.md", "CHANGES.md", "HISTORY.md"],
        "has_adr_directory": ["docs/adr", "adr", "docs/architecture/decisions"],
        "has_sast_config": [".semgrep.yml", ".semgrep.yaml", ".semgrep"],
        "has_dast_config": [".zap/rules.tsv", "dast-config.yml", ".dast.yml"],
        "has_api_docs": ["openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json", "docs/api"],
        "has_runbook": ["runbook.md", "docs/runbook.md", "RUNBOOK.md"],
        "has_sla_document": ["SLA.md", "docs/SLA.md", "docs/sla.md"],
        "has_migration_guide": ["MIGRATION.md", "docs/migration.md", "docs/MIGRATION.md"],
        "has_deprecation_policy": ["DEPRECATION.md", "docs/deprecation.md", "docs/DEPRECATION.md"],
        "has_issue_templates": [".gitlab/issue_templates"],
        "has_branching_strategy_doc": ["docs/branching-strategy.md", "docs/git-workflow.md", "BRANCHING.md"],
        "has_release_process_doc": ["docs/release-process.md", "RELEASING.md", "docs/RELEASING.md"],
        "has_hotfix_process_doc": ["docs/hotfix-process.md", "docs/HOTFIX.md"],
        "has_definition_of_done": ["docs/definition-of-done.md", "docs/DOD.md"],
        "has_feature_flags": [".featureflags.yml", "feature-flags.json", "flagsmith.json", "launchdarkly.yml"],
        "has_editorconfig": [".editorconfig", ".prettierrc", ".prettierrc.json", ".prettierrc.yml"],
        "has_type_checking": ["mypy.ini", ".mypy.ini", "pyproject.toml", "tsconfig.json", "pyrightconfig.json"],
        "has_dr_runbook": ["docs/disaster-recovery.md", "docs/DR.md", "DR-RUNBOOK.md"],
        "has_incident_response_playbook": ["docs/incident-response.md", "docs/INCIDENT.md", "INCIDENT-RESPONSE.md", "playbooks/incident.md"],
        "has_on_call_doc": ["docs/on-call.md", "docs/oncall.md", "ON-CALL.md"],
        "has_dashboards_as_code": ["grafana/dashboards", "dashboards/", "monitoring/dashboards"],
    }

    ref = getattr(project, "default_branch", "main") or "main"

    for flag, paths in candidate_paths.items():
        for path in paths:
            try:
                project.files.get(file_path=path, ref=ref)
                flags[flag] = True
                break
            except GitlabError:
                continue

    # Check project features that are API attributes rather than files
    try:
        flags["has_wiki"] = bool(getattr(project, "wiki_enabled", False))
    except (GitlabError, AttributeError):
        pass

    try:
        flags["has_discussions_enabled"] = bool(getattr(project, "issues_enabled", False))
    except (GitlabError, AttributeError):
        pass

    return flags


def _fetch_recent_mrs(project: Any, count: int = 30) -> list[PullRequestInfo]:
    """Retrieve the last *count* merged merge requests."""
    prs: list[PullRequestInfo] = []
    try:
        merge_requests = project.mergerequests.list(
            state="merged",
            order_by="updated_at",
            sort="desc",
            per_page=count,
        )
        for mr in merge_requests:
            review_count = 0
            try:
                approvals = mr.approvals.get()
                review_count = len(getattr(approvals, "approved_by", []) or [])
            except GitlabError:
                pass

            changes = getattr(mr, "changes_count", None)
            # GitLab changes_count is a string like "5"
            additions = 0
            deletions = 0
            if changes:
                try:
                    total = int(changes)
                    additions = total // 2
                    deletions = total - additions
                except (ValueError, TypeError):
                    pass

            prs.append(
                PullRequestInfo(
                    number=mr.iid,
                    title=mr.title,
                    additions=additions,
                    deletions=deletions,
                    review_count=review_count,
                    merged=True,
                    created_at=_parse_datetime(mr.created_at),
                )
            )
    except GitlabError as exc:
        logger.debug("Could not fetch MRs for %s: %s", project.path_with_namespace, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error fetching MRs for %s: %s", project.path_with_namespace, exc)
    return prs
