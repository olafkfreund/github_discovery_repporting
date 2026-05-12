from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.tools.base import ToolError, WorkspaceContext
from backend.agents.tools.git_diff import GitDiff
from backend.agents.tools.git_status import GitStatus


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceContext:
    return WorkspaceContext(path=tmp_path, head_sha="abc123")


def _make_mock_subprocess(
    stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0
) -> MagicMock:
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    mock_proc.communicate = AsyncMock(return_value=(stdout, stderr))
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()
    return mock_proc


class TestGitDiff:
    async def test_no_revs_runs_git_diff(self, workspace: WorkspaceContext) -> None:
        mock_proc = _make_mock_subprocess(stdout=b"diff output", returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await GitDiff()({}, workspace=workspace, provider=None)
        args = mock_exec.call_args[0]
        assert args[0] == "git"
        assert args[1] == "diff"
        assert result.ok
        assert "diff output" in result.output

    async def test_rev_a_and_rev_b_passed_in_order(self, workspace: WorkspaceContext) -> None:
        mock_proc = _make_mock_subprocess(stdout=b"between commits", returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await GitDiff()(
                {"rev_a": "abc", "rev_b": "def"},
                workspace=workspace,
                provider=None,
            )
        args = mock_exec.call_args[0]
        assert list(args) == ["git", "diff", "abc", "def"]
        assert result.ok
        assert result.metadata["rev_a"] == "abc"
        assert result.metadata["rev_b"] == "def"

    async def test_only_rev_a_no_rev_b(self, workspace: WorkspaceContext) -> None:
        """rev_a without rev_b: git diff <rev_a> (shows diff from that commit to HEAD)."""
        mock_proc = _make_mock_subprocess(stdout=b"diff from sha", returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await GitDiff()(
                {"rev_a": "deadbeef"},
                workspace=workspace,
                provider=None,
            )
        args = mock_exec.call_args[0]
        assert list(args) == ["git", "diff", "deadbeef"]
        assert result.ok

    async def test_rev_b_without_rev_a_raises(self, workspace: WorkspaceContext) -> None:
        with pytest.raises(ToolError, match="rev_b requires rev_a"):
            await GitDiff()(
                {"rev_b": "def"},
                workspace=workspace,
                provider=None,
            )

    async def test_nonzero_exit_ok_false(self, workspace: WorkspaceContext) -> None:
        mock_proc = _make_mock_subprocess(stderr=b"fatal error", returncode=128)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await GitDiff()({}, workspace=workspace, provider=None)
        assert not result.ok
        assert result.metadata["exit_code"] == 128


class TestGitStatus:
    async def test_invokes_porcelain_v1(self, workspace: WorkspaceContext) -> None:
        mock_proc = _make_mock_subprocess(stdout=b"M  file.py\n", returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await GitStatus()({}, workspace=workspace, provider=None)
        args = mock_exec.call_args[0]
        assert list(args) == ["git", "status", "--porcelain=v1"]
        assert result.ok
        assert "file.py" in result.output

    async def test_clean_tree_empty_output(self, workspace: WorkspaceContext) -> None:
        mock_proc = _make_mock_subprocess(stdout=b"", returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await GitStatus()({}, workspace=workspace, provider=None)
        assert result.ok
        assert result.output == ""

    async def test_nonzero_exit_ok_false(self, workspace: WorkspaceContext) -> None:
        mock_proc = _make_mock_subprocess(stderr=b"not a git repo", returncode=128)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await GitStatus()({}, workspace=workspace, provider=None)
        assert not result.ok
        assert "not a git repo" in result.output
