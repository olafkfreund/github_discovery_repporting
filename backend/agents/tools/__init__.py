from __future__ import annotations

from typing import Any

from backend.agents.tools.base import Tool, ToolCall, ToolError, ToolResult, WorkspaceContext
from backend.agents.tools.edit_file import EditFile
from backend.agents.tools.git_diff import GitDiff
from backend.agents.tools.git_status import GitStatus
from backend.agents.tools.provider_api import ProviderApi
from backend.agents.tools.read_file import ReadFile
from backend.agents.tools.recipe_success_check import RecipeSuccessCheck
from backend.agents.tools.run_command import RunCommand
from backend.agents.tools.write_file import WriteFile


def get_tool_registry() -> dict[str, Tool]:
    """Return the immutable allow-list of tools.

    Order matches the natural priority (file ops first, run_command next,
    provider/recipe last). The LLM cannot extend this set; attempting to
    invoke a tool not in this dict is the loop's responsibility (raises
    ToolError("Tool '<name>' is not in the allow-list") at dispatch).
    """
    return {
        ReadFile.name: ReadFile(),
        WriteFile.name: WriteFile(),
        EditFile.name: EditFile(),
        RunCommand.name: RunCommand(),
        GitDiff.name: GitDiff(),
        GitStatus.name: GitStatus(),
        ProviderApi.name: ProviderApi(),
        RecipeSuccessCheck.name: RecipeSuccessCheck(),
    }


def tool_schemas() -> list[dict[str, Any]]:
    """Return the LLM-facing tool schemas (name, description, parameters)."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.arguments_schema,
        }
        for t in get_tool_registry().values()
    ]


__all__ = [
    "Tool",
    "ToolCall",
    "ToolError",
    "ToolResult",
    "WorkspaceContext",
    "get_tool_registry",
    "tool_schemas",
]
