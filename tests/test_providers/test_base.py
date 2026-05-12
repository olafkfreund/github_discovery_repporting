from __future__ import annotations

import inspect
from typing import Any

import pytest

from backend.providers.azure_devops import AzureDevOpsProvider
from backend.providers.base import ProviderWriteError
from backend.providers.github import GitHubProvider
from backend.providers.gitlab import GitLabProvider

# ---------------------------------------------------------------------------
# Expected new method names that must exist on every provider
# ---------------------------------------------------------------------------
_WRITE_METHODS = [
    "create_branch",
    "commit_files",
    "create_pull_request",
    "get_pr_status",
    "set_branch_protection",
]

# Required parameter names for each write method (subset that all providers share)
_METHOD_PARAMS: dict[str, list[str]] = {
    "create_branch": ["self", "repo", "branch", "from_sha"],
    "commit_files": ["self", "repo", "branch", "files", "message", "author_name", "author_email"],
    "create_pull_request": ["self", "repo", "head", "base", "title", "body", "draft"],
    "get_pr_status": ["self", "repo", "pr_number"],
    "set_branch_protection": ["self", "repo", "branch", "rules"],
}


# ---------------------------------------------------------------------------
# Fixtures — providers constructed without network calls
# ---------------------------------------------------------------------------


@pytest.fixture()
def github_provider() -> GitHubProvider:
    """GitHubProvider using a fake token; uses the default github.com allowlist."""
    return GitHubProvider(token="fake-token", org_name="fake-org")


@pytest.fixture()
def gitlab_provider() -> GitLabProvider:
    """GitLabProvider using a fake token; uses the default gitlab.com allowlist."""
    return GitLabProvider(token="fake-token", group="fake-group")


@pytest.fixture()
def azure_provider() -> AzureDevOpsProvider:
    """AzureDevOpsProvider using a fake token and org name."""
    return AzureDevOpsProvider(token="fake-token", org_name="fake-org")


# ---------------------------------------------------------------------------
# Helper: parametrize over all three providers
# ---------------------------------------------------------------------------


def _provider_instances(
    github_provider: GitHubProvider,
    gitlab_provider: GitLabProvider,
    azure_provider: AzureDevOpsProvider,
) -> list[tuple[str, Any]]:
    return [
        ("GitHubProvider", github_provider),
        ("GitLabProvider", gitlab_provider),
        ("AzureDevOpsProvider", azure_provider),
    ]


# ---------------------------------------------------------------------------
# ProviderWriteError
# ---------------------------------------------------------------------------


class TestProviderWriteError:
    def test_is_runtime_error_subclass(self) -> None:
        """ProviderWriteError must be a subclass of RuntimeError."""
        assert issubclass(ProviderWriteError, RuntimeError)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(ProviderWriteError, match="something went wrong"):
            raise ProviderWriteError("something went wrong")

    def test_caught_as_runtime_error(self) -> None:
        with pytest.raises(RuntimeError):
            raise ProviderWriteError("caught as base class")


# ---------------------------------------------------------------------------
# Protocol surface — method existence and parameter names
# ---------------------------------------------------------------------------


class TestProviderMethodSignatures:
    @pytest.mark.parametrize("method_name", _WRITE_METHODS)
    def test_github_has_method(self, method_name: str, github_provider: GitHubProvider) -> None:
        assert hasattr(github_provider, method_name), (
            f"GitHubProvider missing method: {method_name}"
        )

    @pytest.mark.parametrize("method_name", _WRITE_METHODS)
    def test_gitlab_has_method(self, method_name: str, gitlab_provider: GitLabProvider) -> None:
        assert hasattr(gitlab_provider, method_name), (
            f"GitLabProvider missing method: {method_name}"
        )

    @pytest.mark.parametrize("method_name", _WRITE_METHODS)
    def test_azure_has_method(self, method_name: str, azure_provider: AzureDevOpsProvider) -> None:
        assert hasattr(azure_provider, method_name), (
            f"AzureDevOpsProvider missing method: {method_name}"
        )

    @pytest.mark.parametrize(
        "provider_cls,method_name",
        [(GitHubProvider, m) for m in _WRITE_METHODS]
        + [(GitLabProvider, m) for m in _WRITE_METHODS]
        + [(AzureDevOpsProvider, m) for m in _WRITE_METHODS],
    )
    def test_method_parameter_names(self, provider_cls: type, method_name: str) -> None:
        """Each method exposes the expected parameter names (checked via inspect)."""
        method = getattr(provider_cls, method_name)
        sig = inspect.signature(method)
        actual_params = list(sig.parameters.keys())
        expected_params = _METHOD_PARAMS[method_name]
        for param in expected_params:
            assert param in actual_params, (
                f"{provider_cls.__name__}.{method_name} is missing parameter {param!r}. "
                f"Got: {actual_params}"
            )


# ---------------------------------------------------------------------------
# Stub behaviour — each stub must raise NotImplementedError
# ---------------------------------------------------------------------------


class TestStubsRaiseNotImplementedError:
    """Verify remaining stubs raise NotImplementedError with an issue reference.

    GitHub (#14) and GitLab (#15) write methods are fully implemented and
    have dedicated test files. Azure DevOps (#16) stubs are the only ones
    that still raise.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method_name", _WRITE_METHODS)
    async def test_azure_stubs_raise(
        self, method_name: str, azure_provider: AzureDevOpsProvider
    ) -> None:
        method = getattr(azure_provider, method_name)
        with pytest.raises(NotImplementedError, match="issue #16"):
            await _call_stub(method, method_name)


# ---------------------------------------------------------------------------
# Helper: call each stub with dummy arguments
# ---------------------------------------------------------------------------


async def _call_stub(method: Any, method_name: str) -> None:
    """Invoke a provider stub method with minimal dummy arguments."""

    from backend.schemas.platform_data import (
        BranchProtectionRules,
        FileChange,
        NormalizedRepo,
    )

    dummy_repo = NormalizedRepo(
        external_id="1",
        name="test-repo",
        url="https://github.com/org/test-repo",
        default_branch="main",
        is_private=False,
    )

    if method_name == "create_branch":
        await method(repo=dummy_repo, branch="new-branch", from_sha="abc123")
    elif method_name == "commit_files":
        await method(
            repo=dummy_repo,
            branch="main",
            files=[FileChange(path="README.md", content="hi", action="update")],
            message="test commit",
        )
    elif method_name == "create_pull_request":
        await method(
            repo=dummy_repo,
            head="feature",
            base="main",
            title="Test PR",
            body="body",
        )
    elif method_name == "get_pr_status":
        await method(repo=dummy_repo, pr_number=1)
    elif method_name == "set_branch_protection":
        await method(repo=dummy_repo, branch="main", rules=BranchProtectionRules())
    else:
        raise ValueError(f"Unknown method: {method_name}")
