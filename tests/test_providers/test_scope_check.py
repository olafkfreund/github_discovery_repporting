"""Unit tests for PlatformProvider.check_write_scope() across all three providers.

Each provider is tested in isolation by mocking the underlying SDK/HTTP calls.
No real network connections are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from gitlab.exceptions import GitlabAuthenticationError

from backend.providers.azure_devops import AzureDevOpsProvider
from backend.providers.github import GitHubProvider
from backend.providers.gitlab import GitLabProvider

# ---------------------------------------------------------------------------
# GitHubProvider.check_write_scope
# ---------------------------------------------------------------------------


@pytest.fixture()
def github_provider() -> GitHubProvider:
    """Return a GitHubProvider without making any real HTTP calls."""
    return GitHubProvider(token="ghp_test", org_name="test-org")


def _stub_github_scopes(provider: GitHubProvider, scopes: list[str] | None) -> None:
    """Set the oauth_scopes on PyGithub's private requester.

    ``Github.oauth_scopes`` is a read-only property that delegates to
    ``Github._Github__requester.oauth_scopes``.  We set the attribute directly
    on the underlying Requester object, which is a plain instance attribute
    (not a property), making it writable.
    """
    requester = provider._client._Github__requester  # type: ignore[attr-defined]
    requester.oauth_scopes = scopes


class TestGitHubCheckWriteScope:
    """Parametrised tests for GitHubProvider.check_write_scope()."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("scopes", "expected"),
        [
            # Both required scopes present → write capable
            (["repo", "workflow"], True),
            # Additional scopes alongside required ones
            (["repo", "workflow", "read:org", "admin:repo_hook"], True),
            # Missing workflow scope → insufficient
            (["repo", "read:org"], False),
            # Missing repo scope → insufficient
            (["workflow", "read:org"], False),
            # Neither scope → insufficient
            (["read:org", "read:user"], False),
            # Empty scope list → insufficient
            ([], False),
        ],
    )
    async def test_scope_combinations(
        self,
        github_provider: GitHubProvider,
        scopes: list[str],
        expected: bool,
    ) -> None:
        """check_write_scope returns True only when both repo and workflow are present."""
        # Stub get_user to be a no-op (the real call populates oauth_scopes via
        # HTTP headers; we inject the scopes directly onto the requester instead).
        with patch.object(github_provider._client, "get_user", return_value=MagicMock()):
            _stub_github_scopes(github_provider, scopes)
            result = await github_provider.check_write_scope()

        assert result is expected

    @pytest.mark.asyncio
    async def test_no_scope_header_returns_none(
        self,
        github_provider: GitHubProvider,
    ) -> None:
        """None is returned when X-OAuth-Scopes header is absent (fine-grained PAT)."""
        with patch.object(github_provider._client, "get_user", return_value=MagicMock()):
            _stub_github_scopes(github_provider, None)
            result = await github_provider.check_write_scope()

        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(
        self,
        github_provider: GitHubProvider,
    ) -> None:
        """Unexpected exceptions during the probe are swallowed and return None."""
        with patch.object(
            github_provider,
            "_run",
            side_effect=RuntimeError("network error"),
        ):
            result = await github_provider.check_write_scope()

        assert result is None


# ---------------------------------------------------------------------------
# GitLabProvider.check_write_scope
# ---------------------------------------------------------------------------


@pytest.fixture()
def gitlab_provider() -> GitLabProvider:
    """Return a GitLabProvider without making any real HTTP calls."""
    with patch("gitlab.Gitlab"):
        return GitLabProvider(token="glpat-test", group="test-group")


def _make_pat_mock(scopes: list[str]) -> MagicMock:
    """Return a mock personal access token object with the given scopes."""
    pat = MagicMock()
    pat.scopes = scopes
    return pat


class TestGitLabCheckWriteScope:
    """Parametrised tests for GitLabProvider.check_write_scope()."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("scopes", "expected"),
        [
            # "api" alone grants full access
            (["api"], True),
            # "api" with other scopes
            (["api", "read_user"], True),
            # Both repo scopes → write capable
            (["read_repository", "write_repository"], True),
            # Both repo scopes plus others
            (["read_api", "read_repository", "write_repository"], True),
            # read_api only → insufficient
            (["read_api"], False),
            # read_repository only → insufficient (write_repository missing)
            (["read_repository"], False),
            # write_repository only → insufficient (read_repository missing)
            (["write_repository"], False),
            # Empty scopes → insufficient
            ([], False),
        ],
    )
    async def test_scope_combinations(
        self,
        gitlab_provider: GitLabProvider,
        scopes: list[str],
        expected: bool,
    ) -> None:
        """check_write_scope returns True for api scope or both repo scopes."""
        pat_mock = _make_pat_mock(scopes)
        gitlab_provider._client.personal_access_tokens = MagicMock()
        gitlab_provider._client.personal_access_tokens.get = MagicMock(return_value=pat_mock)

        result = await gitlab_provider.check_write_scope()

        assert result is expected

    @pytest.mark.asyncio
    async def test_authentication_error_returns_none(
        self,
        gitlab_provider: GitLabProvider,
    ) -> None:
        """GitlabAuthenticationError (group/deploy tokens) causes None return."""
        gitlab_provider._client.personal_access_tokens = MagicMock()
        gitlab_provider._client.personal_access_tokens.get = MagicMock(
            side_effect=GitlabAuthenticationError("401: Unauthorized")
        )

        result = await gitlab_provider.check_write_scope()

        assert result is None

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_none(
        self,
        gitlab_provider: GitLabProvider,
    ) -> None:
        """Unexpected exceptions during the probe are swallowed and return None."""
        with patch.object(
            gitlab_provider,
            "_run",
            side_effect=ConnectionError("timeout"),
        ):
            result = await gitlab_provider.check_write_scope()

        assert result is None


# ---------------------------------------------------------------------------
# AzureDevOpsProvider.check_write_scope
# ---------------------------------------------------------------------------


@pytest.fixture()
def azure_provider() -> AzureDevOpsProvider:
    """Return an AzureDevOpsProvider without connecting to Azure."""
    with patch("httpx.AsyncClient"):
        return AzureDevOpsProvider(token="azpat-test", org_name="test-org")


class TestAzureDevOpsCheckWriteScope:
    """Tests for AzureDevOpsProvider.check_write_scope().

    Azure DevOps does not expose a PAT scope introspection endpoint, so
    check_write_scope() always returns None (documented limitation).
    """

    @pytest.mark.asyncio
    async def test_always_returns_none(self, azure_provider: AzureDevOpsProvider) -> None:
        """check_write_scope returns None for Azure DevOps — scope unknown."""
        result = await azure_provider.check_write_scope()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_regardless_of_connection_state(
        self, azure_provider: AzureDevOpsProvider
    ) -> None:
        """None is returned even if the provider has not validated its connection."""
        # No mock needed — the method should not make any HTTP calls.
        result = await azure_provider.check_write_scope()
        assert result is None
