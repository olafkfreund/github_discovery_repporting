from __future__ import annotations

import base64
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse

import httpx
import yaml

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
    WorkflowRun,
)

logger = logging.getLogger(__name__)

# Keywords used to classify CI pipeline intent from name / content.
_TEST_KEYWORDS = frozenset({"test", "tests", "testing", "pytest", "jest", "rspec", "vstest"})
_LINT_KEYWORDS = frozenset({"lint", "linting", "flake8", "eslint", "ruff", "rubocop"})
_SECURITY_KEYWORDS = frozenset(
    {"security", "codeql", "trivy", "snyk", "bandit", "semgrep", "gitleaks", "credscan"}
)
_DEPLOY_KEYWORDS = frozenset({"deploy", "release", "publish", "ship", "cd"})

# Candidate paths for file-flag detection — mirrors the GitHub/GitLab providers.
_CANDIDATE_PATHS: dict[str, list[str]] = {
    "has_codeowners": ["CODEOWNERS", ".azure-pipelines/CODEOWNERS", "docs/CODEOWNERS"],
    "has_pr_template": [
        ".azuredevops/pull_request_template.md",
        "pull_request_template.md",
        "docs/pull_request_template.md",
    ],
    "has_contributing_guide": ["CONTRIBUTING.md", "docs/CONTRIBUTING.md"],
    "has_license": ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "LICENCE.md"],
    "has_readme": ["README.md", "README.rst", "README.txt", "README"],
    "has_sbom": ["sbom.json", "sbom.spdx", "sbom.cyclonedx.json", "bom.json", "bom.xml"],
    "has_dockerfile": ["Dockerfile", "dockerfile", "docker/Dockerfile"],
    "has_docker_compose": [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ],
    "has_container_scanning": [".trivy.yaml", ".grype.yaml"],
    "has_iac_files": [
        "main.tf",
        "terraform/main.tf",
        "Pulumi.yaml",
        "pulumi/Pulumi.yaml",
        "infrastructure/main.tf",
    ],
    "has_monitoring_config": [
        "prometheus.yml",
        "monitoring/prometheus.yml",
        "datadog.yaml",
        ".datadog-ci.json",
    ],
    "has_backup_config": ["backup.yml", "backup.yaml", "docs/backup-strategy.md"],
    "has_changelog": ["CHANGELOG.md", "CHANGES.md", "HISTORY.md"],
    "has_adr_directory": ["docs/adr", "adr", "docs/architecture/decisions"],
    "has_sast_config": [".semgrep.yml", ".semgrep.yaml", ".semgrep"],
    "has_dast_config": [".zap/rules.tsv", "dast-config.yml", ".dast.yml"],
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
    "has_deprecation_policy": [
        "DEPRECATION.md",
        "docs/deprecation.md",
        "docs/DEPRECATION.md",
    ],
    "has_issue_templates": [".azuredevops/ISSUE_TEMPLATE"],
    "has_branching_strategy_doc": [
        "docs/branching-strategy.md",
        "docs/git-workflow.md",
        "BRANCHING.md",
    ],
    "has_release_process_doc": [
        "docs/release-process.md",
        "RELEASING.md",
        "docs/RELEASING.md",
    ],
    "has_hotfix_process_doc": ["docs/hotfix-process.md", "docs/HOTFIX.md"],
    "has_definition_of_done": ["docs/definition-of-done.md", "docs/DOD.md"],
    "has_feature_flags": [
        ".featureflags.yml",
        "feature-flags.json",
        "flagsmith.json",
        "launchdarkly.yml",
    ],
    "has_editorconfig": [
        ".editorconfig",
        ".prettierrc",
        ".prettierrc.json",
        ".prettierrc.yml",
    ],
    "has_type_checking": [
        "mypy.ini",
        ".mypy.ini",
        "pyproject.toml",
        "tsconfig.json",
        "pyrightconfig.json",
    ],
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

# Default page size for paginated Azure DevOps API calls.
_PAGE_SIZE = 100

# Circuit breaker: maximum projects to enumerate before stopping pagination.
_MAX_PROJECTS = 500

# Guard: maximum tree items to process in file flag detection.
_MAX_TREE_ITEMS = 50_000

# Validation: Azure DevOps org names may contain alphanumerics, hyphens, and
# underscores (1-50 chars).
_SAFE_ORG_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")

# Allowlist for Azure DevOps hostnames (cloud + legacy).
_ALLOWED_AZURE_HOSTS = re.compile(
    r"^(.*\.)?(dev\.azure\.com|visualstudio\.com|azure\.com)$"
)


class AzureDevOpsProvider:
    """Azure DevOps implementation of the :class:`~backend.providers.base.PlatformProvider` protocol.

    Uses ``httpx.AsyncClient`` for direct async HTTP calls to the Azure DevOps
    REST API v7.0.  Authentication is via a Personal Access Token (PAT) sent
    as Basic auth (``:{pat}``).

    Args:
        token: A Personal Access Token (PAT) with at minimum ``Code (Read)``
            and ``Project and Team (Read)`` scopes.
        org_name: The Azure DevOps organisation name as it appears in the URL
            (e.g. ``"myorg"`` for ``dev.azure.com/myorg``).
        base_url: Optional override for the Azure DevOps REST API base URL.
            Useful for Azure DevOps Server (on-premises) deployments.
    """

    platform: Platform = Platform.azure_devops

    def __init__(
        self,
        token: str,
        org_name: str,
        base_url: str | None = None,
    ) -> None:
        # Validate org_name to prevent URL injection / path traversal.
        if not _SAFE_ORG_NAME.match(org_name):
            raise ValueError(
                f"org_name {org_name!r} contains invalid characters. "
                "Expected alphanumeric characters, dots, hyphens, or underscores."
            )
        self._org_name = org_name

        # Build Basic auth header: base64(":{pat}")
        b64 = base64.b64encode(f":{token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {b64}",
            "Accept": "application/json",
        }

        if base_url:
            # Validate base_url: require HTTPS and a recognised Azure DevOps host.
            parsed = urlparse(base_url)
            if parsed.scheme != "https":
                raise ValueError(
                    "base_url must use HTTPS to protect credentials in transit. "
                    f"Got scheme: {parsed.scheme!r}"
                )
            if not _ALLOWED_AZURE_HOSTS.match(parsed.hostname or ""):
                raise ValueError(
                    f"base_url host {parsed.hostname!r} is not a recognised "
                    "Azure DevOps domain (expected *.dev.azure.com or "
                    "*.visualstudio.com)."
                )
            self._base_url = base_url.rstrip("/")
            self._vssps_url = self._base_url
        else:
            self._base_url = f"https://dev.azure.com/{org_name}"
            self._vssps_url = f"https://vssps.dev.azure.com/{org_name}"

        self._client = httpx.AsyncClient(headers=headers, timeout=30.0)

    # ------------------------------------------------------------------
    # Resource lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client and release connection pool resources."""
        await self._client.aclose()

    async def __aenter__(self) -> AzureDevOpsProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        api_version: str = "7.0",
    ) -> dict[str, Any]:
        """Issue a GET request and return the parsed JSON response.

        Raises ``httpx.HTTPStatusError`` on 4xx/5xx responses.
        """
        merged_params = {"api-version": api_version}
        if params:
            merged_params.update(params)

        resp = await self._client.get(url, params=merged_params)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def _get_with_headers(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        api_version: str = "7.0",
    ) -> tuple[dict[str, Any], httpx.Headers]:
        """Like :meth:`_get` but also returns the response headers.

        Used for APIs that paginate via continuation tokens in response
        headers (e.g. the Graph API).
        """
        merged_params = {"api-version": api_version}
        if params:
            merged_params.update(params)

        resp = await self._client.get(url, params=merged_params)
        resp.raise_for_status()
        return resp.json(), resp.headers

    @staticmethod
    def _parse_external_id(external_id: str) -> tuple[str, str]:
        """Parse ``"project_name:repo_guid"`` back into its components.

        Raises:
            ValueError: If *external_id* does not contain a ``":"`` separator.
        """
        project, sep, repo_id = external_id.partition(":")
        if not sep:
            raise ValueError(
                f"Malformed external_id {external_id!r} — expected 'project:repo_guid' format."
            )
        return project, repo_id

    @staticmethod
    def _quote_path(segment: str) -> str:
        """URL-encode a path segment for safe interpolation into API URLs."""
        return quote(segment, safe="")

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
            await self._get(
                f"{self._base_url}/_apis/projects",
                params={"$top": "1"},
            )
            return True
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Azure DevOps connection validation failed for org=%r: HTTP %s",
                self._org_name,
                exc.response.status_code,
            )
            return False
        except Exception:  # noqa: BLE001
            logger.error(
                "Unexpected error validating Azure DevOps connection for org=%r",
                self._org_name,
                exc_info=True,
            )
            return False

    async def list_repos(self) -> list[NormalizedRepo]:
        """Enumerate all Git repositories across all projects in the organisation.

        Azure DevOps nests repositories under projects, so we first paginate
        through projects, then fetch repos per project.

        Returns:
            A list of :class:`~backend.schemas.platform_data.NormalizedRepo`
            instances.  ``external_id`` is encoded as ``"project:repo_guid"``
            to preserve project context.
        """
        repos: list[NormalizedRepo] = []

        # Paginate projects with circuit breaker
        skip = 0
        total_projects_seen = 0
        while True:
            try:
                data = await self._get(
                    f"{self._base_url}/_apis/projects",
                    params={"$top": str(_PAGE_SIZE), "$skip": str(skip)},
                )
            except Exception:  # noqa: BLE001
                logger.error(
                    "Failed to list projects for org=%r", self._org_name, exc_info=True
                )
                break

            projects: list[dict[str, Any]] = data.get("value", [])
            if not projects:
                break

            for project in projects:
                project_name: str = project["name"]
                project_visibility = project.get("visibility", "private")
                project_path = quote(project_name, safe="")
                try:
                    repo_data = await self._get(
                        f"{self._base_url}/{project_path}/_apis/git/repositories",
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Failed to list repos for project=%r",
                        project_name,
                        exc_info=True,
                    )
                    continue

                for r in repo_data.get("value", []):
                    default_branch = (r.get("defaultBranch") or "refs/heads/main")
                    # Strip the "refs/heads/" prefix
                    if default_branch.startswith("refs/heads/"):
                        default_branch = default_branch[len("refs/heads/"):]

                    repos.append(
                        NormalizedRepo(
                            external_id=f"{project_name}:{r['id']}",
                            name=r["name"],
                            url=r.get("webUrl", r.get("remoteUrl", "")),
                            default_branch=default_branch,
                            is_private=project_visibility != "public",
                            description=r.get("project", {}).get("description"),
                            language=None,
                            created_at=None,
                            updated_at=None,
                            topics=[],
                        )
                    )

            total_projects_seen += len(projects)
            if total_projects_seen >= _MAX_PROJECTS:
                logger.warning(
                    "Reached project limit (%d) for org=%r — stopping enumeration.",
                    _MAX_PROJECTS,
                    self._org_name,
                )
                break
            if len(projects) < _PAGE_SIZE:
                break
            skip += _PAGE_SIZE

        return repos

    async def get_repo_assessment_data(
        self,
        repo: NormalizedRepo,
    ) -> RepoAssessmentData:
        """Collect all assessment data for a single repository.

        Fetches branch policies, build definitions, security features, file
        flags, and recent PR metadata.
        """
        raw_project, repo_id = self._parse_external_id(repo.external_id)
        project = self._quote_path(raw_project)

        branch_protection = await self._fetch_branch_protection(
            project, repo_id, repo.default_branch
        )
        ci_workflows = await self._fetch_ci_workflows(project, repo_id)
        security = await self._fetch_security_features(project, repo_id)
        file_flags = await self._fetch_file_flags(project, repo_id)
        recent_prs = await self._fetch_recent_prs(project, repo_id)

        return RepoAssessmentData(
            repo=repo,
            branch_protection=branch_protection,
            ci_workflows=ci_workflows,
            security=security,
            recent_prs=recent_prs,
            **file_flags,
        )

    async def get_org_assessment_data(self) -> OrgAssessmentData:
        """Collect organisation-level assessment data from Azure DevOps."""

        # Membership stats via VSSPS Graph API (with continuation-token pagination)
        members = OrgMemberInfo(total_members=0, admin_count=0)
        try:
            total_users = 0
            continuation: str | None = None
            while True:
                params: dict[str, str] = {}
                if continuation:
                    params["continuationToken"] = continuation
                data, headers = await self._get_with_headers(
                    f"{self._vssps_url}/_apis/graph/users",
                    params=params,
                    api_version="7.0-preview.1",
                )
                total_users += len(data.get("value", []))
                continuation = headers.get("X-MS-ContinuationToken")
                if not continuation:
                    break
            members.total_members = total_users
        except Exception:  # noqa: BLE001
            logger.debug("Could not fetch user count for %s", self._org_name, exc_info=True)

        # Admin count — enumerate members of admin groups (not just group count).
        try:
            admin_descriptors: set[str] = set()
            continuation = None
            while True:
                params = {}
                if continuation:
                    params["continuationToken"] = continuation
                data, headers = await self._get_with_headers(
                    f"{self._vssps_url}/_apis/graph/groups",
                    params=params,
                    api_version="7.0-preview.1",
                )
                admin_keywords = {
                    "project collection administrators",
                    "project administrators",
                }
                for g in data.get("value", []):
                    display = (g.get("displayName") or "").lower()
                    if any(kw in display for kw in admin_keywords):
                        descriptor = g.get("descriptor", "")
                        if descriptor:
                            # Fetch group members to count actual admin users
                            try:
                                members_data = await self._get(
                                    f"{self._vssps_url}/_apis/graph/memberships/{descriptor}",
                                    params={"direction": "Down"},
                                    api_version="7.0-preview.1",
                                )
                                for m in members_data.get("value", []):
                                    member_url = m.get("memberUrl", "")
                                    admin_descriptors.add(member_url)
                            except Exception:  # noqa: BLE001
                                # Fallback: count the group itself as 1 admin
                                admin_descriptors.add(descriptor)
                continuation = headers.get("X-MS-ContinuationToken")
                if not continuation:
                    break
            members.admin_count = len(admin_descriptors)
        except Exception:  # noqa: BLE001
            logger.debug("Could not fetch group info for %s", self._org_name, exc_info=True)

        # MFA/SSO — managed at Azure AD/Entra ID level, not available via
        # the Azure DevOps REST API.  Keeping False here; the scanner layer
        # should treat these as not_applicable for Azure DevOps.
        members.mfa_enforced = False
        members.sso_enabled = False

        # Security settings — limited visibility via the API
        security_settings = OrgSecuritySettings()

        # Org-level security policy — check for SECURITY.md in first few projects
        has_security_policy = False
        try:
            projects_data = await self._get(
                f"{self._base_url}/_apis/projects",
                params={"$top": "3"},
            )
            for proj in projects_data.get("value", []):
                proj_path = self._quote_path(proj.get("name", ""))
                try:
                    repos_data = await self._get(
                        f"{self._base_url}/{proj_path}/_apis/git/repositories",
                    )
                    for r in repos_data.get("value", []):
                        try:
                            await self._get(
                                f"{self._base_url}/{proj_path}/_apis/git/repositories/{r['id']}/items",
                                params={"path": "SECURITY.md"},
                            )
                            has_security_policy = True
                            break
                        except httpx.HTTPStatusError:
                            continue
                    if has_security_policy:
                        break
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            logger.debug(
                "Could not check org security policy for %s",
                self._org_name,
                exc_info=True,
            )

        return OrgAssessmentData(
            org_name=self._org_name,
            members=members,
            security_settings=security_settings,
            has_org_level_security_policy=has_security_policy,
            billing_plan=None,
        )

    # ------------------------------------------------------------------
    # Private async helpers
    # ------------------------------------------------------------------

    async def _fetch_branch_protection(
        self,
        project: str,
        repo_id: str,
        default_branch: str,
    ) -> BranchProtection | None:
        """Retrieve branch policy configurations scoped to the default branch.

        Azure DevOps uses branch policies (not protection rules).  We map:
        - ``"Minimum number of reviewers"`` → ``required_reviews``, ``dismiss_stale_reviews``
        - ``"Required reviewers"`` → ``require_code_owner_reviews``
        """
        try:
            data = await self._get(
                f"{self._base_url}/{project}/_apis/policy/configurations",
                params={
                    "repositoryId": repo_id,
                    "refName": f"refs/heads/{default_branch}",
                },
            )
        except Exception:  # noqa: BLE001
            logger.debug(
                "Could not fetch branch policies for %s/%s",
                project,
                default_branch,
                exc_info=True,
            )
            return None

        policies = data.get("value", [])
        if not policies:
            return BranchProtection(
                is_protected=False,
                required_reviews=0,
                dismiss_stale_reviews=False,
                require_code_owner_reviews=False,
                enforce_admins=False,
                allow_force_pushes=False,
                require_signed_commits=False,
            )

        required_reviews = 0
        dismiss_stale = False
        require_code_owner = False

        for policy in policies:
            if not policy.get("isEnabled", False):
                continue
            type_name = policy.get("type", {}).get("displayName", "")

            if "minimum number of reviewers" in type_name.lower():
                settings = policy.get("settings", {})
                required_reviews = max(
                    required_reviews,
                    settings.get("minimumApproverCount", 0),
                )
                dismiss_stale = dismiss_stale or settings.get(
                    "resetOnSourcePush", False
                )

            if "required reviewers" in type_name.lower():
                require_code_owner = True

        return BranchProtection(
            is_protected=True,
            required_reviews=required_reviews,
            dismiss_stale_reviews=dismiss_stale,
            require_code_owner_reviews=require_code_owner,
            enforce_admins=False,
            allow_force_pushes=False,
            require_signed_commits=False,
        )

    async def _fetch_ci_workflows(
        self,
        project: str,
        repo_id: str,
    ) -> list[CIWorkflow]:
        """Discover build definitions (CI pipelines) associated with a repository."""
        workflows: list[CIWorkflow] = []

        try:
            data = await self._get(
                f"{self._base_url}/{project}/_apis/build/definitions",
                params={"repositoryId": repo_id, "repositoryType": "TfsGit"},
            )
        except Exception:  # noqa: BLE001
            logger.debug(
                "Could not fetch build definitions for %s/%s",
                project,
                repo_id,
                exc_info=True,
            )
            return workflows

        for defn in data.get("value", []):
            defn_name = defn.get("name", "unknown")
            defn_id = defn.get("id", 0)
            yaml_path = defn.get("process", {}).get("yamlFilename", "")

            # Try to fetch the YAML content for classification
            yaml_content = ""
            if yaml_path:
                try:
                    item_data = await self._get(
                        f"{self._base_url}/{project}/_apis/git/repositories/{repo_id}/items",
                        params={"path": yaml_path, "includeContent": "true"},
                    )
                    yaml_content = item_data.get("content", "")
                    # Azure DevOps may return base64-encoded content
                    encoding = (
                        item_data.get("contentMetadata", {}).get("encoding", "")
                    )
                    if encoding and "base64" in encoding.lower():
                        try:
                            yaml_content = base64.b64decode(yaml_content).decode()
                        except Exception:  # noqa: BLE001
                            yaml_content = ""
                except Exception:  # noqa: BLE001
                    pass

            # Classify workflow intent
            full_text = (defn_name + " " + yaml_content).lower()
            word_set = set(full_text.split())
            has_tests = bool(_TEST_KEYWORDS & word_set)
            has_lint = bool(_LINT_KEYWORDS & word_set)
            has_security = bool(_SECURITY_KEYWORDS & word_set)
            has_deploy = bool(_DEPLOY_KEYWORDS & word_set)

            # Determine trigger events from the YAML
            trigger_events: list[str] = []
            if yaml_content:
                try:
                    parsed = yaml.safe_load(yaml_content)
                    if isinstance(parsed, dict):
                        trigger = parsed.get("trigger")
                        if trigger is None:
                            # `trigger: none` in YAML → explicitly disabled
                            trigger_events = ["none"]
                        elif isinstance(trigger, list):
                            trigger_events = [str(t) for t in trigger]
                        elif isinstance(trigger, dict):
                            branches = trigger.get("branches", {})
                            include = branches.get("include", [])
                            trigger_events = [str(b) for b in include]
                        elif isinstance(trigger, str):
                            trigger_events = [trigger]

                        pr_trigger = parsed.get("pr")
                        if pr_trigger:
                            trigger_events.append("pull_request")
                except Exception:  # noqa: BLE001
                    pass

            if not trigger_events:
                trigger_events = ["push"]

            # Fetch recent build runs
            recent_runs: list[dict[str, Any]] = []
            try:
                builds_data = await self._get(
                    f"{self._base_url}/{project}/_apis/build/builds",
                    params={
                        "definitions": str(defn_id),
                        "$top": "5",
                    },
                )
                recent_runs = builds_data.get("value", [])
            except Exception:  # noqa: BLE001
                pass

            parsed_runs: list[WorkflowRun] = []
            for run in recent_runs:
                parsed_runs.append(
                    WorkflowRun(
                        status=run.get("status", "unknown"),
                        conclusion=run.get("result"),
                        duration_seconds=None,
                        created_at=_parse_datetime(run.get("startTime")),
                    )
                )

            workflows.append(
                CIWorkflow(
                    name=defn_name,
                    path=yaml_path or f"definition:{defn_id}",
                    trigger_events=trigger_events,
                    has_tests=has_tests,
                    has_lint=has_lint,
                    has_security_scan=has_security,
                    has_deploy=has_deploy,
                    recent_runs=parsed_runs,
                )
            )

        return workflows

    async def _fetch_security_features(
        self,
        project: str,
        repo_id: str,
    ) -> SecurityFeatures:
        """Probe security feature states for the repository.

        Azure DevOps Advanced Security (secret scanning, code scanning) is a
        paid feature that may not be enabled.  We gracefully degrade on 404s.
        """
        has_security_policy = False
        secret_scanning = False
        code_scanning = False
        dependabot = False

        # Check SECURITY.md
        try:
            await self._get(
                f"{self._base_url}/{project}/_apis/git/repositories/{repo_id}/items",
                params={"path": "SECURITY.md"},
            )
            has_security_policy = True
        except httpx.HTTPStatusError:
            pass
        except Exception:  # noqa: BLE001
            pass

        # Check pipeline YAML for security tasks
        try:
            for yaml_path in ("azure-pipelines.yml", ".azure-pipelines.yml"):
                try:
                    item_data = await self._get(
                        f"{self._base_url}/{project}/_apis/git/repositories/{repo_id}/items",
                        params={"path": yaml_path, "includeContent": "true"},
                    )
                    content = (item_data.get("content") or "").lower()
                    if any(kw in content for kw in ("credscan", "secret", "gitleaks")):
                        secret_scanning = True
                    if any(kw in content for kw in ("codeql", "sast", "semgrep", "bandit")):
                        code_scanning = True
                    break
                except httpx.HTTPStatusError:
                    continue
        except Exception:  # noqa: BLE001
            pass

        # Check for dependency scanning / renovate config
        for dep_path in (".github/dependabot.yml", "renovate.json", ".renovaterc.json"):
            try:
                await self._get(
                    f"{self._base_url}/{project}/_apis/git/repositories/{repo_id}/items",
                    params={"path": dep_path},
                )
                dependabot = True
                break
            except httpx.HTTPStatusError:
                continue
            except Exception:  # noqa: BLE001
                continue

        return SecurityFeatures(
            dependabot_enabled=dependabot,
            secret_scanning_enabled=secret_scanning,
            code_scanning_enabled=code_scanning,
            vulnerability_alerts=[],
            has_security_policy=has_security_policy,
        )

    async def _fetch_file_flags(
        self,
        project: str,
        repo_id: str,
    ) -> dict[str, bool]:
        """Check for the presence of key repository files.

        Optimised: fetches the full repository tree in one API call and checks
        all candidate paths against the returned set.
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

        # Fetch full repository tree in one call
        tree_paths: set[str] = set()
        try:
            data = await self._get(
                f"{self._base_url}/{project}/_apis/git/repositories/{repo_id}/items",
                params={
                    "recursionLevel": "full",
                    "includeContentMetadata": "false",
                },
            )
            items = data.get("value", [])
            if len(items) > _MAX_TREE_ITEMS:
                logger.warning(
                    "Repo tree for %s/%s has %d items (limit %d) — "
                    "file flag detection may be incomplete.",
                    project,
                    repo_id,
                    len(items),
                    _MAX_TREE_ITEMS,
                )
                items = items[:_MAX_TREE_ITEMS]
            for item in items:
                path = item.get("path", "")
                # Normalise: strip leading "/" for matching
                tree_paths.add(path.lstrip("/"))
        except Exception:  # noqa: BLE001
            logger.debug(
                "Could not fetch repo tree for %s/%s",
                project,
                repo_id,
                exc_info=True,
            )
            return flags

        # Match candidate paths against tree
        for flag, paths in _CANDIDATE_PATHS.items():
            for candidate in paths:
                # Check exact match or prefix match (for directories)
                if candidate in tree_paths or any(
                    p.startswith(candidate) for p in tree_paths
                ):
                    flags[flag] = True
                    break

        # Wiki — project-level feature in Azure DevOps
        try:
            wiki_data = await self._get(
                f"{self._base_url}/{project}/_apis/wiki/wikis",
            )
            if wiki_data.get("value"):
                flags["has_wiki"] = True
        except Exception:  # noqa: BLE001
            pass

        # Project boards (Azure Boards / work items)
        try:
            await self._get(
                f"{self._base_url}/{project}/_apis/work/boards",
            )
            flags["has_project_boards"] = True
        except Exception:  # noqa: BLE001
            pass

        return flags

    async def _fetch_recent_prs(
        self,
        project: str,
        repo_id: str,
        count: int = 30,
    ) -> list[PullRequestInfo]:
        """Retrieve recent completed pull requests.

        Note: ``additions`` and ``deletions`` are always ``0`` because the
        Azure DevOps PR list endpoint does not include line-change counts.
        Fetching per-PR iteration stats would re-introduce N+1 queries.
        Scanners that rely on PR size (e.g. SDLC-004) should treat ``0``
        as "data unavailable" for this platform.
        """
        prs: list[PullRequestInfo] = []

        try:
            data = await self._get(
                f"{self._base_url}/{project}/_apis/git/repositories/{repo_id}/pullrequests",
                params={
                    "searchCriteria.status": "completed",
                    "$top": str(count),
                },
            )
        except Exception:  # noqa: BLE001
            logger.debug(
                "Could not fetch PRs for %s/%s",
                project,
                repo_id,
                exc_info=True,
            )
            return prs

        for pr in data.get("value", []):
            pr_id = pr.get("pullRequestId", 0)

            # The list endpoint includes reviewers inline — no extra API call needed.
            review_count = sum(
                1
                for reviewer in pr.get("reviewers", [])
                if reviewer.get("vote", 0) != 0
            )

            prs.append(
                PullRequestInfo(
                    number=pr_id,
                    title=pr.get("title", ""),
                    additions=0,
                    deletions=0,
                    review_count=review_count,
                    merged=True,
                    created_at=_parse_datetime(pr.get("creationDate")),
                )
            )

        return prs


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string from Azure DevOps."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, AttributeError):
        return None
