from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from backend.providers.github import GitHubProvider
from backend.schemas.platform_data import NormalizedRepo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider() -> GitHubProvider:
    """Return a GitHubProvider configured for a test organisation.

    The underlying PyGithub ``Github`` client is never used directly in these
    tests; individual methods are patched at the ``_run`` / client level.
    """
    return GitHubProvider(token="ghp_test_token", org_name="test-org")


def _make_mock_repo(
    *,
    repo_id: int = 1,
    name: str = "test-repo",
    html_url: str = "https://github.com/test-org/test-repo",
    default_branch: str = "main",
    private: bool = False,
    description: str | None = "A test repository",
    language: str | None = "Python",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    topics: list[str] | None = None,
) -> MagicMock:
    """Build a MagicMock that mimics a PyGithub ``Repository`` object."""
    repo = MagicMock()
    repo.id = repo_id
    repo.name = name
    repo.html_url = html_url
    repo.default_branch = default_branch
    repo.private = private
    repo.description = description
    repo.language = language
    repo.created_at = created_at or datetime(2023, 1, 1, tzinfo=UTC)
    repo.updated_at = updated_at or datetime(2024, 6, 1, tzinfo=UTC)
    repo.get_topics.return_value = topics or []
    return repo


# ---------------------------------------------------------------------------
# validate_connection tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_connection_success(provider: GitHubProvider) -> None:
    """validate_connection returns True when get_organization succeeds."""
    mock_org = MagicMock()

    with patch.object(provider._client, "get_organization", return_value=mock_org):
        result = await provider.validate_connection()

    assert result is True


@pytest.mark.asyncio
async def test_validate_connection_failure_github_exception(
    provider: GitHubProvider,
) -> None:
    """validate_connection returns False when PyGithub raises GithubException."""
    exc = GithubException(status=401, data={"message": "Bad credentials"}, headers={})

    with patch.object(provider._client, "get_organization", side_effect=exc):
        result = await provider.validate_connection()

    assert result is False


@pytest.mark.asyncio
async def test_validate_connection_failure_generic_exception(
    provider: GitHubProvider,
) -> None:
    """validate_connection returns False on any unexpected exception."""
    with patch.object(
        provider._client,
        "get_organization",
        side_effect=ConnectionError("network failure"),
    ):
        result = await provider.validate_connection()

    assert result is False


@pytest.mark.asyncio
async def test_validate_connection_404_org_not_found(provider: GitHubProvider) -> None:
    """validate_connection returns False when the organisation cannot be found."""
    exc = GithubException(status=404, data={"message": "Not Found"}, headers={})

    with patch.object(provider._client, "get_organization", side_effect=exc):
        result = await provider.validate_connection()

    assert result is False


# ---------------------------------------------------------------------------
# list_repos tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_repos_returns_normalized_repos(provider: GitHubProvider) -> None:
    """list_repos converts PyGithub Repository objects to NormalizedRepo instances."""
    mock_repo_a = _make_mock_repo(repo_id=1, name="repo-alpha", language="Python")
    mock_repo_b = _make_mock_repo(repo_id=2, name="repo-beta", language="Go")

    mock_org = MagicMock()
    mock_org.get_repos.return_value = [mock_repo_a, mock_repo_b]

    with patch.object(provider._client, "get_organization", return_value=mock_org):
        repos = await provider.list_repos()

    assert len(repos) == 2
    assert all(isinstance(r, NormalizedRepo) for r in repos)

    names = {r.name for r in repos}
    assert names == {"repo-alpha", "repo-beta"}


@pytest.mark.asyncio
async def test_list_repos_empty_org(provider: GitHubProvider) -> None:
    """list_repos returns an empty list when the organisation has no repos."""
    mock_org = MagicMock()
    mock_org.get_repos.return_value = []

    with patch.object(provider._client, "get_organization", return_value=mock_org):
        repos = await provider.list_repos()

    assert repos == []


@pytest.mark.asyncio
async def test_list_repos_field_mapping(provider: GitHubProvider) -> None:
    """list_repos maps PyGithub fields to NormalizedRepo attributes correctly."""
    mock_repo = _make_mock_repo(
        repo_id=42,
        name="my-service",
        html_url="https://github.com/test-org/my-service",
        default_branch="develop",
        private=True,
        description="Service description",
        language="TypeScript",
        topics=["kubernetes", "microservices"],
    )
    mock_org = MagicMock()
    mock_org.get_repos.return_value = [mock_repo]

    with patch.object(provider._client, "get_organization", return_value=mock_org):
        repos = await provider.list_repos()

    assert len(repos) == 1
    repo = repos[0]

    assert repo.external_id == "42"
    assert repo.name == "my-service"
    assert repo.url == "https://github.com/test-org/my-service"
    assert repo.default_branch == "develop"
    assert repo.is_private is True
    assert repo.description == "Service description"
    assert repo.language == "TypeScript"
    assert set(repo.topics) == {"kubernetes", "microservices"}


@pytest.mark.asyncio
async def test_list_repos_none_default_branch_falls_back_to_main(
    provider: GitHubProvider,
) -> None:
    """list_repos substitutes 'main' when default_branch is None on the PyGithub object."""
    mock_repo = _make_mock_repo(name="legacy-repo")
    mock_repo.default_branch = None  # Simulate missing default_branch

    mock_org = MagicMock()
    mock_org.get_repos.return_value = [mock_repo]

    with patch.object(provider._client, "get_organization", return_value=mock_org):
        repos = await provider.list_repos()

    assert repos[0].default_branch == "main"


# ---------------------------------------------------------------------------
# Provider construction tests
# ---------------------------------------------------------------------------


def test_provider_uses_public_github_without_base_url() -> None:
    """GitHubProvider without base_url creates a public github.com client."""
    prov = GitHubProvider(token="tok", org_name="my-org")
    # The client should be a Github instance (not GithubEnterprise).
    assert prov._client is not None
    assert prov._org_name == "my-org"


def test_provider_uses_enterprise_url_when_supplied() -> None:
    """GitHubProvider with base_url creates a client targeting that URL."""
    prov = GitHubProvider(
        token="tok",
        org_name="my-org",
        base_url="https://github.example.com/api/v3",
    )
    assert prov._base_url == "https://github.example.com/api/v3"
    assert prov._client is not None


def test_provider_platform_attribute() -> None:
    """GitHubProvider.platform is always Platform.github."""
    from backend.models.enums import Platform

    prov = GitHubProvider(token="tok", org_name="org")
    assert prov.platform == Platform.github
