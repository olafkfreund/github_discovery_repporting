from __future__ import annotations

from pathlib import Path

import pytest

from backend.agents.tools.base import ToolError, WorkspaceContext
from backend.agents.tools.write_file import WriteFile


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceContext:
    return WorkspaceContext(path=tmp_path, head_sha="abc123")


@pytest.fixture()
def tool() -> WriteFile:
    return WriteFile()


class TestWriteFileHappyPath:
    async def test_create_new_file(self, tool: WriteFile, workspace: WorkspaceContext) -> None:
        result = await tool(
            {"path": "new_file.txt", "content": "hello"},
            workspace=workspace,
            provider=None,
        )

        assert result.ok
        assert result.metadata["created"] is True
        assert (workspace.path / "new_file.txt").read_text() == "hello"

    async def test_overwrite_existing_file(
        self, tool: WriteFile, workspace: WorkspaceContext
    ) -> None:
        target = workspace.path / "existing.txt"
        target.write_text("old content")

        result = await tool(
            {"path": "existing.txt", "content": "new content"},
            workspace=workspace,
            provider=None,
        )

        assert result.ok
        assert result.metadata["created"] is False
        assert target.read_text() == "new content"

    async def test_creates_parent_directories(
        self, tool: WriteFile, workspace: WorkspaceContext
    ) -> None:
        result = await tool(
            {"path": "deep/nested/dir/file.txt", "content": "deep"},
            workspace=workspace,
            provider=None,
        )

        assert result.ok
        assert (workspace.path / "deep" / "nested" / "dir" / "file.txt").exists()

    async def test_bytes_written_metadata(
        self, tool: WriteFile, workspace: WorkspaceContext
    ) -> None:
        content = "abc"
        result = await tool(
            {"path": "file.txt", "content": content},
            workspace=workspace,
            provider=None,
        )

        assert result.metadata["bytes_written"] == len(content.encode())


class TestWriteFileErrors:
    @pytest.mark.parametrize(
        "path",
        [
            "../outside.txt",
            "../../etc/passwd",
        ],
    )
    async def test_path_traversal_raises(
        self, tool: WriteFile, workspace: WorkspaceContext, path: str
    ) -> None:
        with pytest.raises(ToolError, match="outside the workspace"):
            await tool(
                {"path": path, "content": "malicious"},
                workspace=workspace,
                provider=None,
            )

    async def test_size_cap_raises(self, tool: WriteFile, workspace: WorkspaceContext) -> None:
        big_content = "X" * (1024 * 1024 + 1)
        with pytest.raises(ToolError, match="exceeds 1 MB cap"):
            await tool(
                {"path": "big.txt", "content": big_content},
                workspace=workspace,
                provider=None,
            )

    async def test_exactly_1mb_succeeds(self, tool: WriteFile, workspace: WorkspaceContext) -> None:
        content = "Y" * (1024 * 1024)
        result = await tool(
            {"path": "limit.txt", "content": content},
            workspace=workspace,
            provider=None,
        )
        assert result.ok
