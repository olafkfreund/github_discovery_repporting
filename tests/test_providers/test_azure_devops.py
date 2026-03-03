from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.models.enums import Platform
from backend.providers.azure_devops import AzureDevOpsProvider
from backend.schemas.platform_data import NormalizedRepo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider() -> AzureDevOpsProvider:
    """Return an AzureDevOpsProvider configured for a test organisation."""
    return AzureDevOpsProvider(token="test-pat", org_name="test-org")


def _mock_response(json_data: dict | list, status_code: int = 200) -> httpx.Response:
    """Build a fake httpx.Response with the given JSON payload."""
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://example.com"),
    )


def _mock_error_response(status_code: int = 404) -> httpx.Response:
    """Build a fake httpx.Response that will raise on raise_for_status."""
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", "https://example.com"),
    )


# ---------------------------------------------------------------------------
# Provider construction tests
# ---------------------------------------------------------------------------


def test_provider_platform_attribute() -> None:
    """AzureDevOpsProvider.platform is always Platform.azure_devops."""
    prov = AzureDevOpsProvider(token="tok", org_name="org")
    assert prov.platform == Platform.azure_devops


def test_provider_uses_public_azure_devops_urls() -> None:
    """Provider without base_url uses dev.azure.com and vssps.dev.azure.com."""
    prov = AzureDevOpsProvider(token="tok", org_name="myorg")
    assert prov._base_url == "https://dev.azure.com/myorg"
    assert prov._vssps_url == "https://vssps.dev.azure.com/myorg"


def test_provider_uses_custom_base_url() -> None:
    """Provider with base_url uses it for both core and vssps APIs."""
    prov = AzureDevOpsProvider(
        token="tok",
        org_name="myorg",
        base_url="https://myorg.visualstudio.com",
    )
    assert prov._base_url == "https://myorg.visualstudio.com"
    assert prov._vssps_url == "https://myorg.visualstudio.com"


def test_provider_rejects_invalid_org_name() -> None:
    """Provider raises ValueError for org names with special characters."""
    with pytest.raises(ValueError, match="invalid characters"):
        AzureDevOpsProvider(token="tok", org_name="../malicious")


def test_provider_rejects_non_https_base_url() -> None:
    """Provider raises ValueError for non-HTTPS base URLs."""
    with pytest.raises(ValueError, match="HTTPS"):
        AzureDevOpsProvider(
            token="tok",
            org_name="myorg",
            base_url="http://dev.azure.com/myorg",
        )


def test_provider_rejects_unknown_host_base_url() -> None:
    """Provider raises ValueError for base URLs with non-Azure DevOps hosts."""
    with pytest.raises(ValueError, match="not a recognised"):
        AzureDevOpsProvider(
            token="tok",
            org_name="myorg",
            base_url="https://evil.example.com/myorg",
        )


# ---------------------------------------------------------------------------
# Resource lifecycle tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_releases_client(provider: AzureDevOpsProvider) -> None:
    """close() calls aclose() on the underlying httpx client."""
    with patch.object(provider._client, "aclose", new_callable=AsyncMock) as mock_aclose:
        await provider.close()
    mock_aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_context_manager() -> None:
    """Provider works as an async context manager."""
    provider = AzureDevOpsProvider(token="tok", org_name="myorg")
    with patch.object(provider._client, "aclose", new_callable=AsyncMock) as mock_aclose:
        async with provider as p:
            assert p is provider
    mock_aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# parse_external_id tests
# ---------------------------------------------------------------------------


def test_parse_external_id() -> None:
    """_parse_external_id splits project:repo_guid correctly."""
    project, repo_id = AzureDevOpsProvider._parse_external_id("MyProject:abc-123-def")
    assert project == "MyProject"
    assert repo_id == "abc-123-def"


def test_parse_external_id_with_colons_in_project() -> None:
    """_parse_external_id handles only the first colon as separator."""
    project, repo_id = AzureDevOpsProvider._parse_external_id("My:Project:abc-123")
    assert project == "My"
    assert repo_id == "Project:abc-123"


# ---------------------------------------------------------------------------
# validate_connection tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_connection_success(provider: AzureDevOpsProvider) -> None:
    """validate_connection returns True when projects API succeeds."""
    mock_get = AsyncMock(return_value=_mock_response({"value": [], "count": 0}))

    with patch.object(provider._client, "get", mock_get):
        result = await provider.validate_connection()

    assert result is True


@pytest.mark.asyncio
async def test_validate_connection_failure_401(provider: AzureDevOpsProvider) -> None:
    """validate_connection returns False on HTTP 401."""
    mock_get = AsyncMock(return_value=_mock_error_response(401))

    with patch.object(provider._client, "get", mock_get):
        result = await provider.validate_connection()

    assert result is False


@pytest.mark.asyncio
async def test_validate_connection_failure_network(provider: AzureDevOpsProvider) -> None:
    """validate_connection returns False on network errors."""
    mock_get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch.object(provider._client, "get", mock_get):
        result = await provider.validate_connection()

    assert result is False


# ---------------------------------------------------------------------------
# list_repos tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_repos_across_projects(provider: AzureDevOpsProvider) -> None:
    """list_repos discovers repos across multiple projects."""
    projects_resp = _mock_response({
        "value": [
            {"name": "ProjectA"},
            {"name": "ProjectB"},
        ],
        "count": 2,
    })
    repos_a_resp = _mock_response({
        "value": [
            {
                "id": "repo-1",
                "name": "service-api",
                "defaultBranch": "refs/heads/main",
                "webUrl": "https://dev.azure.com/test-org/ProjectA/_git/service-api",
                "project": {"description": "API service"},
            },
        ],
    })
    repos_b_resp = _mock_response({
        "value": [
            {
                "id": "repo-2",
                "name": "frontend",
                "defaultBranch": "refs/heads/develop",
                "webUrl": "https://dev.azure.com/test-org/ProjectB/_git/frontend",
                "project": {},
            },
        ],
    })

    async def mock_get(url: str, **kwargs: object) -> httpx.Response:
        url_str = str(url)
        if "/_apis/projects" in url_str:
            return projects_resp
        if "ProjectA/_apis/git/repositories" in url_str:
            return repos_a_resp
        if "ProjectB/_apis/git/repositories" in url_str:
            return repos_b_resp
        return _mock_response({"value": []})

    with patch.object(provider._client, "get", side_effect=mock_get):
        repos = await provider.list_repos()

    assert len(repos) == 2
    assert all(isinstance(r, NormalizedRepo) for r in repos)

    names = {r.name for r in repos}
    assert names == {"service-api", "frontend"}

    # Verify external_id encoding
    api_repo = next(r for r in repos if r.name == "service-api")
    assert api_repo.external_id == "ProjectA:repo-1"

    # Verify branch prefix stripping
    fe_repo = next(r for r in repos if r.name == "frontend")
    assert fe_repo.default_branch == "develop"


@pytest.mark.asyncio
async def test_list_repos_strips_refs_heads(provider: AzureDevOpsProvider) -> None:
    """list_repos strips 'refs/heads/' prefix from default branches."""
    projects_resp = _mock_response({"value": [{"name": "P1"}], "count": 1})
    repos_resp = _mock_response({
        "value": [
            {
                "id": "r1",
                "name": "my-repo",
                "defaultBranch": "refs/heads/release/v2",
                "webUrl": "https://dev.azure.com/test-org/P1/_git/my-repo",
                "project": {},
            },
        ],
    })

    async def mock_get(url: str, **kwargs: object) -> httpx.Response:
        if "/_apis/projects" in str(url):
            return projects_resp
        return repos_resp

    with patch.object(provider._client, "get", side_effect=mock_get):
        repos = await provider.list_repos()

    assert repos[0].default_branch == "release/v2"


# ---------------------------------------------------------------------------
# Branch protection tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_branch_protection_reviewer_policy(provider: AzureDevOpsProvider) -> None:
    """_fetch_branch_protection extracts reviewer count from branch policies."""
    policies_resp = _mock_response({
        "value": [
            {
                "isEnabled": True,
                "type": {"displayName": "Minimum number of reviewers"},
                "settings": {
                    "minimumApproverCount": 2,
                    "resetOnSourcePush": True,
                },
            },
            {
                "isEnabled": True,
                "type": {"displayName": "Required reviewers"},
                "settings": {},
            },
        ],
    })

    with patch.object(provider._client, "get", AsyncMock(return_value=policies_resp)):
        result = await provider._fetch_branch_protection("Proj", "repo-1", "main")

    assert result is not None
    assert result.is_protected is True
    assert result.required_reviews == 2
    assert result.dismiss_stale_reviews is True
    assert result.require_code_owner_reviews is True


@pytest.mark.asyncio
async def test_branch_protection_no_policies(provider: AzureDevOpsProvider) -> None:
    """_fetch_branch_protection returns unprotected when no policies exist."""
    empty_resp = _mock_response({"value": []})

    with patch.object(provider._client, "get", AsyncMock(return_value=empty_resp)):
        result = await provider._fetch_branch_protection("Proj", "repo-1", "main")

    assert result is not None
    assert result.is_protected is False
    assert result.required_reviews == 0


# ---------------------------------------------------------------------------
# CI workflows tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ci_workflows_from_definitions(provider: AzureDevOpsProvider) -> None:
    """_fetch_ci_workflows discovers build definitions and classifies intent."""
    definitions_resp = _mock_response({
        "value": [
            {
                "id": 10,
                "name": "CI Build",
                "process": {"yamlFilename": "azure-pipelines.yml"},
            },
        ],
    })
    yaml_content = "trigger:\n  - main\nsteps:\n  - script: pytest tests/"
    yaml_resp = _mock_response({"content": yaml_content})
    builds_resp = _mock_response({"value": []})

    call_count = 0

    async def mock_get(url: str, **kwargs: object) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        url_str = str(url)
        if "build/definitions" in url_str:
            return definitions_resp
        if "/items" in url_str:
            return yaml_resp
        if "build/builds" in url_str:
            return builds_resp
        return _mock_response({"value": []})

    with patch.object(provider._client, "get", side_effect=mock_get):
        workflows = await provider._fetch_ci_workflows("Proj", "repo-1")

    assert len(workflows) == 1
    wf = workflows[0]
    assert wf.name == "CI Build"
    assert wf.has_tests is True
    assert "main" in wf.trigger_events


# ---------------------------------------------------------------------------
# File flags tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_flags_tree_based(provider: AzureDevOpsProvider) -> None:
    """_fetch_file_flags uses tree-based bulk fetch to detect files."""
    tree_resp = _mock_response({
        "value": [
            {"path": "/README.md"},
            {"path": "/LICENSE"},
            {"path": "/Dockerfile"},
            {"path": "/docs/adr/001-use-postgres.md"},
            {"path": "/.editorconfig"},
            {"path": "/mypy.ini"},
        ],
    })

    with patch.object(provider._client, "get", AsyncMock(return_value=tree_resp)):
        flags = await provider._fetch_file_flags("Proj", "repo-1")

    assert flags["has_readme"] is True
    assert flags["has_license"] is True
    assert flags["has_dockerfile"] is True
    assert flags["has_adr_directory"] is True
    assert flags["has_editorconfig"] is True
    assert flags["has_type_checking"] is True
    # Absent files should be False
    assert flags["has_sbom"] is False
    assert flags["has_docker_compose"] is False


# ---------------------------------------------------------------------------
# Recent PRs tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recent_prs_with_reviewers(provider: AzureDevOpsProvider) -> None:
    """_fetch_recent_prs counts reviewers who voted (inline, no N+1)."""
    prs_resp = _mock_response({
        "value": [
            {
                "pullRequestId": 42,
                "title": "Add auth middleware",
                "creationDate": "2024-06-15T10:30:00Z",
                "reviewers": [
                    {"vote": 10, "displayName": "Alice"},
                    {"vote": 0, "displayName": "Bot"},
                    {"vote": -5, "displayName": "Bob"},
                ],
            },
        ],
    })

    with patch.object(provider._client, "get", AsyncMock(return_value=prs_resp)):
        prs = await provider._fetch_recent_prs("Proj", "repo-1")

    assert len(prs) == 1
    pr = prs[0]
    assert pr.number == 42
    assert pr.title == "Add auth middleware"
    assert pr.review_count == 2  # Alice (vote=10) and Bob (vote=-5); Bot (vote=0) excluded
    assert pr.merged is True


# ---------------------------------------------------------------------------
# Org assessment tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_assessment_data(provider: AzureDevOpsProvider) -> None:
    """get_org_assessment_data collects membership stats and security policy."""
    users_resp = _mock_response({
        "value": [
            {"displayName": "User1"},
            {"displayName": "User2"},
            {"displayName": "User3"},
        ],
    })
    groups_resp = _mock_response({
        "value": [
            {
                "displayName": "Project Collection Administrators",
                "descriptor": "vssgp.admin1",
            },
            {"displayName": "Contributors", "descriptor": "vssgp.contrib"},
            {
                "displayName": "Project Administrators",
                "descriptor": "vssgp.admin2",
            },
        ],
    })
    # Admin group 1 members
    admin1_members_resp = _mock_response({
        "value": [
            {"memberUrl": "https://vssps.dev.azure.com/_apis/graph/users/user1"},
            {"memberUrl": "https://vssps.dev.azure.com/_apis/graph/users/user2"},
        ],
    })
    # Admin group 2 members (user2 overlaps with group 1)
    admin2_members_resp = _mock_response({
        "value": [
            {"memberUrl": "https://vssps.dev.azure.com/_apis/graph/users/user2"},
            {"memberUrl": "https://vssps.dev.azure.com/_apis/graph/users/user3"},
        ],
    })
    projects_resp = _mock_response({"value": [{"name": "Proj1"}]})
    repos_resp = _mock_response({
        "value": [{"id": "r1", "name": "repo1"}],
    })
    security_md_resp = _mock_response({"path": "/SECURITY.md"})

    async def mock_get(url: str, **kwargs: object) -> httpx.Response:
        url_str = str(url)
        if "graph/memberships/vssgp.admin1" in url_str:
            return admin1_members_resp
        if "graph/memberships/vssgp.admin2" in url_str:
            return admin2_members_resp
        if "graph/users" in url_str:
            return users_resp
        if "graph/groups" in url_str:
            return groups_resp
        if "/_apis/projects" in url_str:
            return projects_resp
        if "/_apis/git/repositories" in url_str and "/items" not in url_str:
            return repos_resp
        if "/items" in url_str:
            return security_md_resp
        return _mock_response({"value": []})

    with patch.object(provider._client, "get", side_effect=mock_get):
        org_data = await provider.get_org_assessment_data()

    assert org_data.org_name == "test-org"
    assert org_data.members is not None
    assert org_data.members.total_members == 3
    # Deduped across admin groups: user1, user2, user3 = 3
    assert org_data.members.admin_count == 3
    assert org_data.members.mfa_enforced is False
    assert org_data.has_org_level_security_policy is True
    assert org_data.billing_plan is None
