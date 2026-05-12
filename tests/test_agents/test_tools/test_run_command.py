from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.tools.base import ToolError, WorkspaceContext
from backend.agents.tools.run_command import _MAX_OUTPUT_BYTES, RunCommand


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceContext:
    return WorkspaceContext(path=tmp_path, head_sha="abc123")


@pytest.fixture()
def tool() -> RunCommand:
    return RunCommand()


def _make_mock_subprocess(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
    """Helper to create a mock asyncio.subprocess.Process."""
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    mock_proc.communicate = AsyncMock(return_value=(stdout, stderr))
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()
    return mock_proc


class TestRunCommandAllowList:
    async def test_allowed_binary_succeeds(
        self, tool: RunCommand, workspace: WorkspaceContext
    ) -> None:
        mock_proc = _make_mock_subprocess(stdout=b"git version 2.40.0", returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await tool(
                {"command": ["git", "--version"]},
                workspace=workspace,
                provider=None,
            )
        mock_exec.assert_called_once()
        assert result.ok
        assert "git version" in result.output

    @pytest.mark.parametrize(
        "binary",
        ["curl", "wget", "bash", "sh", "python", "pip", "npm", "rm"],
    )
    async def test_non_allowed_binary_raises_before_subprocess(
        self, tool: RunCommand, workspace: WorkspaceContext, binary: str
    ) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            with pytest.raises(ToolError, match="not allow-listed"):
                await tool(
                    {"command": [binary, "--help"]},
                    workspace=workspace,
                    provider=None,
                )
            mock_exec.assert_not_called()

    @pytest.mark.parametrize(
        "binary",
        ["git", "pre-commit", "ruff", "yamllint", "trivy", "terraform"],
    )
    async def test_all_allowed_binaries_accepted(
        self, tool: RunCommand, workspace: WorkspaceContext, binary: str
    ) -> None:
        mock_proc = _make_mock_subprocess(returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            # Just verify no ToolError is raised for the allow-check itself
            result = await tool(
                {"command": [binary, "--version"]},
                workspace=workspace,
                provider=None,
            )
        # ok=True if exit code was 0
        assert result.ok


class TestRunCommandOutput:
    async def test_nonzero_exit_code_ok_false(
        self, tool: RunCommand, workspace: WorkspaceContext
    ) -> None:
        mock_proc = _make_mock_subprocess(stdout=b"", stderr=b"error occurred", returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await tool(
                {"command": ["git", "status"]},
                workspace=workspace,
                provider=None,
            )
        assert not result.ok
        assert result.metadata["exit_code"] == 1

    async def test_oversized_stdout_truncated(
        self, tool: RunCommand, workspace: WorkspaceContext
    ) -> None:
        big_output = b"X" * (_MAX_OUTPUT_BYTES + 1000)
        mock_proc = _make_mock_subprocess(stdout=big_output, returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await tool(
                {"command": ["git", "log"]},
                workspace=workspace,
                provider=None,
            )
        # stdout_bytes in metadata should reflect the truncated length
        assert result.metadata["stdout_bytes"] <= _MAX_OUTPUT_BYTES

    async def test_output_contains_command_header(
        self, tool: RunCommand, workspace: WorkspaceContext
    ) -> None:
        mock_proc = _make_mock_subprocess(stdout=b"output", returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await tool(
                {"command": ["git", "--version"]},
                workspace=workspace,
                provider=None,
            )
        assert "$ git --version" in result.output


class TestRunCommandTimeout:
    async def test_timeout_raises_tool_error(
        self, tool: RunCommand, workspace: WorkspaceContext
    ) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(ToolError, match="timed out"):
                await tool(
                    {"command": ["git", "clone"], "timeout_seconds": 1},
                    workspace=workspace,
                    provider=None,
                )
