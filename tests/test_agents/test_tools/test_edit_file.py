from __future__ import annotations

from pathlib import Path

import pytest

from backend.agents.tools.base import ToolError, WorkspaceContext
from backend.agents.tools.edit_file import EditFile


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceContext:
    return WorkspaceContext(path=tmp_path, head_sha="abc123")


@pytest.fixture()
def tool() -> EditFile:
    return EditFile()


class TestEditFileHappyPath:
    async def test_unique_match_replaces(self, tool: EditFile, workspace: WorkspaceContext) -> None:
        target = workspace.path / "code.py"
        target.write_text("def foo():\n    return 1\n")

        result = await tool(
            {
                "path": "code.py",
                "old_string": "return 1",
                "new_string": "return 42",
            },
            workspace=workspace,
            provider=None,
        )

        assert result.ok
        assert result.metadata["occurrences"] == 1
        assert "return 42" in target.read_text()
        assert "return 1" not in target.read_text()

    async def test_bytes_diff_in_metadata(
        self, tool: EditFile, workspace: WorkspaceContext
    ) -> None:
        target = workspace.path / "file.txt"
        target.write_text("old")

        result = await tool(
            {"path": "file.txt", "old_string": "old", "new_string": "longer_new"},
            workspace=workspace,
            provider=None,
        )

        assert result.ok
        # "longer_new" (10 bytes) - "old" (3 bytes) = +7
        assert result.metadata["bytes_diff"] == 7

    async def test_only_first_occurrence_replaced_when_unique(
        self, tool: EditFile, workspace: WorkspaceContext
    ) -> None:
        """Verify we do not accidentally replace 2+ occurrences."""
        target = workspace.path / "dup.txt"
        # Two occurrences must be caught and rejected
        target.write_text("hello hello")

        with pytest.raises(ToolError, match="matched 2 times"):
            await tool(
                {"path": "dup.txt", "old_string": "hello", "new_string": "world"},
                workspace=workspace,
                provider=None,
            )


class TestEditFileErrors:
    async def test_no_match_raises(self, tool: EditFile, workspace: WorkspaceContext) -> None:
        target = workspace.path / "file.txt"
        target.write_text("some content")

        with pytest.raises(ToolError, match="not found"):
            await tool(
                {
                    "path": "file.txt",
                    "old_string": "missing text",
                    "new_string": "replacement",
                },
                workspace=workspace,
                provider=None,
            )

    async def test_multiple_matches_raises_with_count(
        self, tool: EditFile, workspace: WorkspaceContext
    ) -> None:
        target = workspace.path / "file.txt"
        target.write_text("a a a")

        with pytest.raises(ToolError, match="matched 3 times"):
            await tool(
                {"path": "file.txt", "old_string": "a", "new_string": "b"},
                workspace=workspace,
                provider=None,
            )

    async def test_path_traversal_raises(self, tool: EditFile, workspace: WorkspaceContext) -> None:
        with pytest.raises(ToolError, match="outside the workspace"):
            await tool(
                {
                    "path": "../evil.txt",
                    "old_string": "x",
                    "new_string": "y",
                },
                workspace=workspace,
                provider=None,
            )

    async def test_nonexistent_file_raises(
        self, tool: EditFile, workspace: WorkspaceContext
    ) -> None:
        with pytest.raises(ToolError, match="not found"):
            await tool(
                {
                    "path": "ghost.txt",
                    "old_string": "x",
                    "new_string": "y",
                },
                workspace=workspace,
                provider=None,
            )
