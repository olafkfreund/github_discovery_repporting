from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from functools import partial
from typing import Any

import yaml
from github import Auth, Github, GithubException
from github.Repository import Repository as GithubRepo

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

# Keywords used to classify CI workflow intent from name / content.
_TEST_KEYWORDS = frozenset({"test", "tests", "testing", "pytest", "jest", "rspec"})
_LINT_KEYWORDS = frozenset({"lint", "linting", "flake8", "eslint", "ruff", "rubocop"})
_SECURITY_KEYWORDS = frozenset(
    {"security", "codeql", "trivy", "snyk", "bandit", "semgrep", "gitleaks"}
)
_DEPLOY_KEYWORDS = frozenset({"deploy", "release", "publish", "ship", "cd"})


class GitHubProvider:
    """GitHub implementation of the :class:`~backend.providers.base.PlatformProvider` protocol.

    All public methods are ``async``.  Because PyGithub exposes a synchronous
    REST client, every blocking call is offloaded to the default
    :class:`~concurrent.futures.ThreadPoolExecutor` via
    :func:`asyncio.get_event_loop().run_in_executor` so that the event loop is
    never stalled.

    Args:
        token: A GitHub Personal Access Token (PAT) or fine-grained token with
            at minimum ``repo`` and ``read:org`` scopes.
        org_name: The GitHub organisation (or user) login whose repositories
            will be enumerated.
        base_url: Optional GitHub Enterprise Server base URL
            (e.g. ``"https://github.example.com/api/v3"``).  When ``None`` the
            public ``api.github.com`` endpoint is used.

    Example::

        provider = GitHubProvider(token="ghp_...", org_name="my-org")
        if await provider.validate_connection():
            repos = await provider.list_repos()
    """

    platform: Platform = Platform.github

    def __init__(
        self,
        token: str,
        org_name: str,
        base_url: str | None = None,
    ) -> None:
        self._token = token
        self._org_name = org_name
        self._base_url = base_url
        auth = Auth.Token(token)
        self._client = Github(base_url=base_url, auth=auth) if base_url else Github(auth=auth)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous callable in the default thread-pool executor.

        This prevents PyGithub's blocking HTTP calls from stalling the
        ``asyncio`` event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    async def validate_connection(self) -> bool:
        """Test that the PAT can reach the target organisation.

        Returns:
            ``True`` if the organisation is accessible, ``False`` on any
            authentication or network failure.
        """
        try:
            await self._run(self._client.get_organization, self._org_name)
            return True
        except GithubException as exc:
            logger.warning(
                "GitHub connection validation failed for org=%r: %s",
                self._org_name,
                exc,
            )
            return False
        except Exception as exc:  # noqa: BLE001 — surface all failures as False
            logger.error(
                "Unexpected error validating GitHub connection for org=%r: %s",
                self._org_name,
                exc,
            )
            return False

    async def list_repos(self) -> list[NormalizedRepo]:
        """Enumerate all repositories in the configured organisation.

        Returns:
            A list of :class:`~backend.schemas.platform_data.NormalizedRepo`
            instances for every repository visible to the token.
        """

        def _fetch() -> list[NormalizedRepo]:
            org = self._client.get_organization(self._org_name)
            repos = org.get_repos()
            results: list[NormalizedRepo] = []
            for r in repos:
                results.append(_normalize_repo(r))
            return results

        return await self._run(_fetch)

    async def get_repo_assessment_data(
        self,
        repo: NormalizedRepo,
    ) -> RepoAssessmentData:
        """Collect the full set of assessment data for a single repository.

        Fetches branch protection, CI workflows, security features, file
        presence checks, and recent PR metadata.  Individual sub-fetches are
        wrapped in ``try/except`` blocks so that partial data is always
        returned even when some API calls fail (e.g. due to token scope
        limitations).

        Args:
            repo: A normalised repo record previously returned by
                :meth:`list_repos`.

        Returns:
            A :class:`~backend.schemas.platform_data.RepoAssessmentData`
            instance populated with all available data.
        """

        def _fetch_all() -> RepoAssessmentData:
            gh_repo = self._client.get_repo(f"{self._org_name}/{repo.name}")
            branch_protection = _fetch_branch_protection(gh_repo, repo.default_branch)
            ci_workflows = _fetch_ci_workflows(gh_repo)
            security = _fetch_security_features(gh_repo)
            file_flags = _fetch_file_flags(gh_repo)
            recent_prs = _fetch_recent_prs(gh_repo)

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
        """Collect organisation-level assessment data from GitHub."""

        def _fetch_org() -> OrgAssessmentData:
            org = self._client.get_organization(self._org_name)

            # Membership stats
            members = OrgMemberInfo(total_members=0, admin_count=0)
            try:
                all_members = list(org.get_members())
                members.total_members = len(all_members)
                admins = list(org.get_members(role="admin"))
                members.admin_count = len(admins)
            except GithubException as exc:
                logger.debug("Could not fetch member counts for %s: %s", self._org_name, exc)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Unexpected error fetching members for %s: %s", self._org_name, exc)

            # 2FA enforcement
            try:
                members.mfa_enforced = bool(org.two_factor_requirement_enabled)
            except (GithubException, AttributeError) as exc:
                logger.debug("Could not check 2FA for %s: %s", self._org_name, exc)

            # Security settings
            security_settings = OrgSecuritySettings()
            try:
                security_settings.default_repo_permission = org.default_repository_permission
                security_settings.members_can_create_public_repos = bool(
                    org.members_can_create_public_repositories
                )
                security_settings.two_factor_requirement_enabled = bool(
                    org.two_factor_requirement_enabled
                )
            except (GithubException, AttributeError) as exc:
                logger.debug(
                    "Could not fetch org security settings for %s: %s", self._org_name, exc
                )

            # Org-level security policy (check .github repo)
            has_security_policy = False
            try:
                dot_github = self._client.get_repo(f"{self._org_name}/.github")
                for path in ("SECURITY.md", "profile/SECURITY.md"):
                    try:
                        dot_github.get_contents(path)
                        has_security_policy = True
                        break
                    except GithubException:
                        continue
            except GithubException:
                pass
            except Exception:  # noqa: BLE001
                pass

            # Billing plan
            billing_plan: str | None = None
            try:
                billing_plan = org.plan.name if org.plan else None
            except (GithubException, AttributeError):
                pass

            return OrgAssessmentData(
                org_name=self._org_name,
                members=members,
                security_settings=security_settings,
                has_org_level_security_policy=has_security_policy,
                billing_plan=billing_plan,
            )

        return await self._run(_fetch_org)


# ---------------------------------------------------------------------------
# Private synchronous helpers — called inside run_in_executor workers
# ---------------------------------------------------------------------------


def _normalize_repo(r: GithubRepo) -> NormalizedRepo:
    """Convert a PyGithub ``Repository`` object to a ``NormalizedRepo``."""
    return NormalizedRepo(
        external_id=str(r.id),
        name=r.name,
        url=r.html_url,
        default_branch=r.default_branch or "main",
        is_private=r.private,
        description=r.description,
        language=r.language,
        created_at=_to_utc(r.created_at),
        updated_at=_to_utc(r.updated_at),
        topics=list(r.get_topics()),
    )


def _to_utc(dt: datetime | None) -> datetime | None:
    """Ensure *dt* is timezone-aware (UTC).  Returns ``None`` for ``None``."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _fetch_branch_protection(
    repo: GithubRepo,
    default_branch: str,
) -> BranchProtection | None:
    """Retrieve branch protection settings for *default_branch*.

    Returns ``None`` if the branch has no protection rules or the token lacks
    the necessary scope (``repo`` + admin).
    """
    try:
        branch = repo.get_branch(default_branch)
        if not branch.protected:
            return BranchProtection(
                is_protected=False,
                required_reviews=0,
                dismiss_stale_reviews=False,
                require_code_owner_reviews=False,
                enforce_admins=False,
                allow_force_pushes=False,
                require_signed_commits=False,
            )
        protection = branch.get_protection()
        required_reviews = 0
        dismiss_stale = False
        codeowner_reviews = False
        try:
            pr_reviews = protection.required_pull_request_reviews
            if pr_reviews is not None:
                required_reviews = pr_reviews.required_approving_review_count or 0
                dismiss_stale = pr_reviews.dismiss_stale_reviews
                codeowner_reviews = pr_reviews.require_code_owner_reviews
        except Exception:  # noqa: BLE001
            pass

        enforce_admins = False
        try:
            enforce_admins = bool(protection.enforce_admins)
        except Exception:  # noqa: BLE001
            pass

        allow_force_pushes = False
        try:
            allow_force_pushes = bool(protection.allow_force_pushes)
        except Exception:  # noqa: BLE001
            pass

        require_signed = False
        try:
            require_signed = bool(protection.required_signatures)
        except Exception:  # noqa: BLE001
            pass

        return BranchProtection(
            is_protected=True,
            required_reviews=required_reviews,
            dismiss_stale_reviews=dismiss_stale,
            require_code_owner_reviews=codeowner_reviews,
            enforce_admins=enforce_admins,
            allow_force_pushes=allow_force_pushes,
            require_signed_commits=require_signed,
        )
    except GithubException as exc:
        logger.debug(
            "Could not fetch branch protection for %s/%s: %s",
            repo.full_name,
            default_branch,
            exc,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Unexpected error fetching branch protection for %s: %s",
            repo.full_name,
            exc,
        )
        return None


def _fetch_ci_workflows(repo: GithubRepo) -> list[CIWorkflow]:
    """Discover and classify CI/CD workflows from ``.github/workflows/``."""
    workflows: list[CIWorkflow] = []
    try:
        contents = repo.get_contents(".github/workflows")
        if not isinstance(contents, list):
            contents = [contents]

        for content_file in contents:
            if not content_file.name.endswith((".yml", ".yaml")):
                continue
            workflow = _parse_workflow_file(content_file)
            if workflow is not None:
                workflows.append(workflow)
    except GithubException as exc:
        logger.debug(
            "No .github/workflows directory found in %s: %s",
            repo.full_name,
            exc,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Error fetching CI workflows for %s: %s",
            repo.full_name,
            exc,
        )
    return workflows


def _parse_workflow_file(content_file: Any) -> CIWorkflow | None:
    """Parse a single workflow YAML file and classify its intent."""
    try:
        raw_yaml = content_file.decoded_content.decode("utf-8")
        workflow_data: dict[str, Any] = yaml.safe_load(raw_yaml) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not parse workflow file %s: %s", content_file.path, exc)
        return None

    name: str = workflow_data.get("name", content_file.name)
    name_lower = name.lower()

    # Parse trigger events from the ``on:`` key.
    on_value = workflow_data.get("on", {})
    if isinstance(on_value, str):
        trigger_events = [on_value]
    elif isinstance(on_value, list):
        trigger_events = [str(e) for e in on_value]
    elif isinstance(on_value, dict):
        trigger_events = list(on_value.keys())
    else:
        trigger_events = []

    # Classify workflow by searching name and full YAML text for keywords.
    full_text = (name_lower + " " + raw_yaml).lower()

    has_tests = bool(_TEST_KEYWORDS & set(full_text.split()))
    has_lint = bool(_LINT_KEYWORDS & set(full_text.split()))
    has_security = bool(_SECURITY_KEYWORDS & set(full_text.split()))
    has_deploy = bool(_DEPLOY_KEYWORDS & set(full_text.split()))

    return CIWorkflow(
        name=name,
        path=content_file.path,
        trigger_events=trigger_events,
        has_tests=has_tests,
        has_lint=has_lint,
        has_security_scan=has_security,
        has_deploy=has_deploy,
        recent_runs=[],  # Workflow run history requires the Actions API
    )


def _fetch_security_features(repo: GithubRepo) -> SecurityFeatures:
    """Probe security feature states for the repository."""
    dependabot = False
    secret_scanning = False
    code_scanning = False
    has_security_policy = False

    # Check for SECURITY.md presence as a proxy for a security policy.
    for path in ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"):
        try:
            repo.get_contents(path)
            has_security_policy = True
            break
        except GithubException:
            pass
        except Exception:  # noqa: BLE001
            pass

    # Dependabot — check for .github/dependabot.yml presence.
    for path in (".github/dependabot.yml", ".github/dependabot.yaml"):
        try:
            repo.get_contents(path)
            dependabot = True
            break
        except GithubException:
            pass
        except Exception:  # noqa: BLE001
            pass

    # Secret scanning and code scanning require elevated token scopes.
    # We attempt to query them but gracefully degrade on 403/404.
    try:
        alerts = list(repo.get_secret_scanning_alerts())
        # If we can list alerts the feature is enabled (even if zero alerts).
        secret_scanning = True
        _ = alerts  # consumed for the side-effect check
    except GithubException as exc:
        if exc.status == 404:
            # Feature not enabled on this repo.
            secret_scanning = False
        else:
            logger.debug(
                "Secret scanning check failed for %s (status=%s)",
                repo.full_name,
                exc.status,
            )
    except Exception:  # noqa: BLE001
        pass

    try:
        alerts = list(repo.get_codescan_alerts())
        code_scanning = True
        _ = alerts
    except GithubException as exc:
        if exc.status == 404:
            code_scanning = False
        else:
            logger.debug(
                "Code scanning check failed for %s (status=%s)",
                repo.full_name,
                exc.status,
            )
    except Exception:  # noqa: BLE001
        pass

    return SecurityFeatures(
        dependabot_enabled=dependabot,
        secret_scanning_enabled=secret_scanning,
        code_scanning_enabled=code_scanning,
        vulnerability_alerts=[],
        has_security_policy=has_security_policy,
    )


def _fetch_file_flags(repo: GithubRepo) -> dict[str, bool]:
    """Check for the presence of key repository files.

    Returns a mapping of flag names to boolean values covering all 16
    scanner domains.
    """
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
        "has_codeowners": ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"],
        "has_pr_template": [
            ".github/pull_request_template.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "pull_request_template.md",
        ],
        "has_contributing_guide": [
            "CONTRIBUTING.md",
            ".github/CONTRIBUTING.md",
            "docs/CONTRIBUTING.md",
        ],
        "has_license": ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "LICENCE.md"],
        "has_readme": ["README.md", "README.rst", "README.txt", "README"],
        "has_sbom": ["sbom.json", "sbom.spdx", "sbom.cyclonedx.json", "bom.json", "bom.xml"],
        # Container
        "has_dockerfile": ["Dockerfile", "dockerfile", "docker/Dockerfile"],
        "has_docker_compose": [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        ],
        "has_container_scanning": [
            ".github/workflows/container-scan.yml",
            ".trivy.yaml",
            ".grype.yaml",
        ],
        # IaC
        "has_iac_files": [
            "main.tf",
            "terraform/main.tf",
            "Pulumi.yaml",
            "pulumi/Pulumi.yaml",
            "infrastructure/main.tf",
        ],
        # Monitoring / Observability
        "has_monitoring_config": [
            "prometheus.yml",
            "monitoring/prometheus.yml",
            "datadog.yaml",
            ".datadog-ci.json",
            "grafana/dashboards",
        ],
        "has_backup_config": ["backup.yml", "backup.yaml", "docs/backup-strategy.md"],
        # Documentation
        "has_changelog": ["CHANGELOG.md", "CHANGES.md", "HISTORY.md"],
        "has_adr_directory": ["docs/adr", "adr", "docs/architecture/decisions"],
        # Security tooling
        "has_sast_config": [
            ".semgrep.yml",
            ".semgrep.yaml",
            ".semgrep",
            ".codeql",
            ".github/codeql",
        ],
        "has_dast_config": [".zap/rules.tsv", "dast-config.yml", ".dast.yml"],
        # API / process docs
        "has_api_docs": [
            "openapi.yaml",
            "openapi.json",
            "swagger.yaml",
            "swagger.json",
            "docs/api",
        ],
        "has_runbook": ["runbook.md", "docs/runbook.md", "RUNBOOK.md"],
        "has_sla_document": ["SLA.md", "docs/SLA.md", "docs/sla.md"],
        "has_migration_guide": ["MIGRATION.md", "docs/migration.md", "docs/MIGRATION.md"],
        "has_deprecation_policy": ["DEPRECATION.md", "docs/deprecation.md", "docs/DEPRECATION.md"],
        # Issue / collaboration
        "has_issue_templates": [".github/ISSUE_TEMPLATE", ".github/ISSUE_TEMPLATE.md"],
        # SDLC / process
        "has_branching_strategy_doc": [
            "docs/branching-strategy.md",
            "docs/git-workflow.md",
            "BRANCHING.md",
        ],
        "has_release_process_doc": ["docs/release-process.md", "RELEASING.md", "docs/RELEASING.md"],
        "has_hotfix_process_doc": ["docs/hotfix-process.md", "docs/HOTFIX.md"],
        "has_definition_of_done": ["docs/definition-of-done.md", "docs/DOD.md"],
        "has_feature_flags": [
            ".featureflags.yml",
            "feature-flags.json",
            "flagsmith.json",
            "launchdarkly.yml",
        ],
        # Code quality
        "has_editorconfig": [".editorconfig", ".prettierrc", ".prettierrc.json", ".prettierrc.yml"],
        "has_type_checking": [
            "mypy.ini",
            ".mypy.ini",
            "pyproject.toml",
            "tsconfig.json",
            "pyrightconfig.json",
        ],
        # DR / incident
        "has_dr_runbook": ["docs/disaster-recovery.md", "docs/DR.md", "DR-RUNBOOK.md"],
        "has_incident_response_playbook": [
            "docs/incident-response.md",
            "docs/INCIDENT.md",
            "INCIDENT-RESPONSE.md",
            "playbooks/incident.md",
        ],
        "has_on_call_doc": ["docs/on-call.md", "docs/oncall.md", "ON-CALL.md"],
        "has_dashboards_as_code": [
            "grafana/dashboards",
            "dashboards/",
            "monitoring/dashboards",
        ],
    }

    for flag, paths in candidate_paths.items():
        for path in paths:
            try:
                repo.get_contents(path)
                flags[flag] = True
                break
            except GithubException:
                continue
            except Exception:  # noqa: BLE001
                continue

    return flags


def _fetch_recent_prs(repo: GithubRepo, count: int = 30) -> list[PullRequestInfo]:
    """Retrieve the last *count* merged pull requests."""
    prs: list[PullRequestInfo] = []
    try:
        pull_requests = repo.get_pulls(state="closed", sort="updated", direction="desc")
        fetched = 0
        for pr in pull_requests:
            if fetched >= count:
                break
            if not pr.merged:
                continue
            try:
                review_count = pr.get_reviews().totalCount
            except Exception:  # noqa: BLE001
                review_count = 0

            prs.append(
                PullRequestInfo(
                    number=pr.number,
                    title=pr.title,
                    additions=pr.additions,
                    deletions=pr.deletions,
                    review_count=review_count,
                    merged=True,
                    created_at=_to_utc(pr.created_at),
                )
            )
            fetched += 1
    except GithubException as exc:
        logger.debug(
            "Could not fetch PRs for %s: %s",
            repo.full_name,
            exc,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Unexpected error fetching PRs for %s: %s",
            repo.full_name,
            exc,
        )
    return prs
