from __future__ import annotations

from pathlib import Path

import pytest

from backend.agents.tools.base import ToolError, WorkspaceContext
from backend.agents.tools.read_file import ReadFile


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceContext:
    return WorkspaceContext(path=tmp_path, head_sha="abc123")


@pytest.fixture()
def tool() -> ReadFile:
    return ReadFile()


class TestReadFileHappyPath:
    async def test_reads_existing_file(self, tool: ReadFile, workspace: WorkspaceContext) -> None:
        target = workspace.path / "hello.txt"
        target.write_text("Hello, world!")

        result = await tool({"path": "hello.txt"}, workspace=workspace, provider=None)

        assert result.ok
        assert "Hello, world!" in result.output
        assert result.metadata["path"] == "hello.txt"
        assert result.metadata["truncated"] is False

    async def test_reads_nested_file(self, tool: ReadFile, workspace: WorkspaceContext) -> None:
        (workspace.path / "sub").mkdir()
        target = workspace.path / "sub" / "file.py"
        target.write_text("x = 1")

        result = await tool({"path": "sub/file.py"}, workspace=workspace, provider=None)

        assert result.ok
        assert "x = 1" in result.output


class TestReadFileTruncation:
    async def test_oversized_file_truncated(
        self, tool: ReadFile, workspace: WorkspaceContext
    ) -> None:
        target = workspace.path / "big.txt"
        # Write 101 KB worth of bytes
        target.write_bytes(b"A" * (101 * 1024))

        result = await tool({"path": "big.txt"}, workspace=workspace, provider=None)

        assert result.ok
        assert result.metadata["truncated"] is True
        assert "[TRUNCATED" in result.output
        assert result.metadata["bytes"] == 100 * 1024

    async def test_exactly_100kb_not_truncated(
        self, tool: ReadFile, workspace: WorkspaceContext
    ) -> None:
        target = workspace.path / "exact.bin"
        target.write_bytes(b"B" * (100 * 1024))

        result = await tool({"path": "exact.bin"}, workspace=workspace, provider=None)

        assert result.ok
        assert result.metadata["truncated"] is False


class TestReadFileErrors:
    @pytest.mark.parametrize(
        "path",
        [
            "../etc/passwd",
            "../../secret",
            "../outside.txt",
        ],
    )
    async def test_path_traversal_raises(
        self, tool: ReadFile, workspace: WorkspaceContext, path: str
    ) -> None:
        with pytest.raises(ToolError, match="outside the workspace"):
            await tool({"path": path}, workspace=workspace, provider=None)

    async def test_nonexistent_file_raises(
        self, tool: ReadFile, workspace: WorkspaceContext
    ) -> None:
        with pytest.raises(ToolError, match="not found"):
            await tool({"path": "does_not_exist.txt"}, workspace=workspace, provider=None)

    async def test_directory_raises(self, tool: ReadFile, workspace: WorkspaceContext) -> None:
        (workspace.path / "mydir").mkdir()
        with pytest.raises(ToolError, match="not a regular file"):
            await tool({"path": "mydir"}, workspace=workspace, provider=None)
