from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from backend.agents.tools.base import ToolError, WorkspaceContext
from backend.agents.tools.provider_api import ProviderApi
from backend.providers.base import PlatformProvider


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceContext:
    return WorkspaceContext(path=tmp_path, head_sha="abc123")


@pytest.fixture()
def tool() -> ProviderApi:
    return ProviderApi()


@pytest.fixture()
def mock_provider() -> MagicMock:
    provider = MagicMock(spec=PlatformProvider)
    provider.create_branch = AsyncMock(return_value=None)
    provider.commit_files = AsyncMock(return_value="deadbeef")
    provider.create_pull_request = AsyncMock(return_value=None)
    provider.set_branch_protection = AsyncMock(return_value=None)
    return provider


class TestProviderApiAllowList:
    @pytest.mark.parametrize(
        "method",
        ["create_branch", "commit_files", "create_pull_request", "set_branch_protection"],
    )
    async def test_allowed_methods_pass_allow_check(
        self,
        tool: ProviderApi,
        workspace: WorkspaceContext,
        mock_provider: MagicMock,
        method: str,
    ) -> None:
        result = await tool(
            {"method": method, "args": {}},
            workspace=workspace,
            provider=mock_provider,
        )
        assert result.ok
        assert result.metadata["method"] == method

    @pytest.mark.parametrize(
        "method",
        [
            "merge_pull_request",
            "get_pr_status",
            "delete_repo",
            "list_repos",
            "validate_connection",
        ],
    )
    async def test_forbidden_methods_raise_before_provider_call(
        self,
        tool: ProviderApi,
        workspace: WorkspaceContext,
        mock_provider: MagicMock,
        method: str,
    ) -> None:
        with pytest.raises(ToolError, match="not allow-listed"):
            await tool(
                {"method": method, "args": {}},
                workspace=workspace,
                provider=mock_provider,
            )
        # Provider must not have been touched
        for attr in ("merge_pull_request", "get_pr_status"):
            assert (
                getattr(mock_provider, attr, None) is None
                or not getattr(mock_provider, attr).called
            )


class TestProviderApiArgForwarding:
    async def test_args_forwarded_as_kwargs(
        self,
        tool: ProviderApi,
        workspace: WorkspaceContext,
        mock_provider: MagicMock,
    ) -> None:
        await tool(
            {
                "method": "create_branch",
                "args": {"repo": "my-repo", "branch": "fix/linting", "from_sha": "abc"},
            },
            workspace=workspace,
            provider=mock_provider,
        )
        mock_provider.create_branch.assert_awaited_once_with(
            repo="my-repo", branch="fix/linting", from_sha="abc"
        )


class TestProviderApiResultSerialisation:
    async def test_pydantic_result_model_dumped(
        self,
        tool: ProviderApi,
        workspace: WorkspaceContext,
        mock_provider: MagicMock,
    ) -> None:
        class FakeResult(BaseModel):
            number: int = 42
            url: str = "https://example.com/pr/1"

        mock_provider.create_pull_request = AsyncMock(return_value=FakeResult())

        result = await tool(
            {"method": "create_pull_request", "args": {}},
            workspace=workspace,
            provider=mock_provider,
        )

        assert result.ok
        assert isinstance(result.metadata["result"], dict)
        assert result.metadata["result"]["number"] == 42

    async def test_non_pydantic_result_stringified(
        self,
        tool: ProviderApi,
        workspace: WorkspaceContext,
        mock_provider: MagicMock,
    ) -> None:
        mock_provider.create_branch = AsyncMock(return_value=None)

        result = await tool(
            {"method": "create_branch", "args": {}},
            workspace=workspace,
            provider=mock_provider,
        )

        assert result.ok
        assert result.metadata["result"] == "None"


class TestProviderApiErrors:
    async def test_missing_method_on_provider_raises(
        self,
        tool: ProviderApi,
        workspace: WorkspaceContext,
    ) -> None:
        bare_provider = MagicMock(spec=[])  # provider with no attributes
        with pytest.raises(ToolError, match="provider has no method"):
            await tool(
                {"method": "create_branch", "args": {}},
                workspace=workspace,
                provider=bare_provider,
            )

    async def test_provider_raises_wrapped_in_tool_error(
        self,
        tool: ProviderApi,
        workspace: WorkspaceContext,
        mock_provider: MagicMock,
    ) -> None:
        mock_provider.create_branch = AsyncMock(side_effect=RuntimeError("network timeout"))
        with pytest.raises(ToolError, match="network timeout"):
            await tool(
                {"method": "create_branch", "args": {}},
                workspace=workspace,
                provider=mock_provider,
            )
