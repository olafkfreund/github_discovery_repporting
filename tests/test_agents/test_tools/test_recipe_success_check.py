from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.tools.base import ToolError, WorkspaceContext
from backend.agents.tools.recipe_success_check import RecipeSuccessCheck


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceContext:
    return WorkspaceContext(path=tmp_path, head_sha="abc123")


@pytest.fixture()
def tool() -> RecipeSuccessCheck:
    return RecipeSuccessCheck()


class TestRecipeSuccessCheckImportMissing:
    async def test_missing_module_raises_tool_error(
        self, tool: RecipeSuccessCheck, workspace: WorkspaceContext
    ) -> None:
        """Simulate the remediation registry not yet being available (issue #25)."""
        with patch.dict(sys.modules, {"backend.remediation.registry": None}):
            with pytest.raises(ToolError, match="remediation registry not yet wired"):
                await tool(
                    {"check_id": "CICD-008"},
                    workspace=workspace,
                    provider=None,
                )

    async def test_missing_parent_package_raises_tool_error(
        self, tool: RecipeSuccessCheck, workspace: WorkspaceContext
    ) -> None:
        """Verify the ImportError path via None sentinel in sys.modules."""
        # Setting a module to None in sys.modules causes ImportError on import.
        with patch.dict(
            sys.modules,
            {"backend.remediation.registry": None, "backend.remediation": None},
        ):
            with pytest.raises(ToolError, match="remediation registry not yet wired"):
                await tool(
                    {"check_id": "REPO-001"},
                    workspace=workspace,
                    provider=None,
                )


class TestRecipeSuccessCheckWhenWired:
    async def test_success_check_returns_true(
        self, tool: RecipeSuccessCheck, workspace: WorkspaceContext
    ) -> None:
        mock_recipe = MagicMock()
        mock_recipe.success_check = AsyncMock(return_value=True)
        mock_get_recipe = MagicMock(return_value=mock_recipe)

        mock_registry_module = MagicMock()
        mock_registry_module.get_recipe = mock_get_recipe

        with patch.dict(sys.modules, {"backend.remediation.registry": mock_registry_module}):
            result = await tool(
                {"check_id": "CICD-008"},
                workspace=workspace,
                provider=None,
            )

        assert result.ok is True
        assert result.metadata["success"] is True
        assert result.metadata["check_id"] == "CICD-008"

    async def test_success_check_returns_false(
        self, tool: RecipeSuccessCheck, workspace: WorkspaceContext
    ) -> None:
        mock_recipe = MagicMock()
        mock_recipe.success_check = AsyncMock(return_value=False)
        mock_get_recipe = MagicMock(return_value=mock_recipe)

        mock_registry_module = MagicMock()
        mock_registry_module.get_recipe = mock_get_recipe

        with patch.dict(sys.modules, {"backend.remediation.registry": mock_registry_module}):
            result = await tool(
                {"check_id": "REPO-003"},
                workspace=workspace,
                provider=None,
            )

        assert result.ok is False
        assert result.metadata["success"] is False

    async def test_no_success_check_on_recipe_raises(
        self, tool: RecipeSuccessCheck, workspace: WorkspaceContext
    ) -> None:
        mock_recipe = MagicMock()
        mock_recipe.success_check = None
        mock_get_recipe = MagicMock(return_value=mock_recipe)

        mock_registry_module = MagicMock()
        mock_registry_module.get_recipe = mock_get_recipe

        with patch.dict(sys.modules, {"backend.remediation.registry": mock_registry_module}):
            with pytest.raises(ToolError, match="no success_check defined"):
                await tool(
                    {"check_id": "SAST-001"},
                    workspace=workspace,
                    provider=None,
                )
