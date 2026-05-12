from __future__ import annotations

import time
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.agents.tools.base import ToolError, ToolResult, WorkspaceContext


class EditFileArgs(BaseModel):
    path: str = Field(..., description="Repository-relative path, no leading slash.")
    old_string: str = Field(
        ...,
        description="The exact text to find. Must occur exactly once in the file.",
    )
    new_string: str = Field(..., description="Replacement text for old_string.")


class EditFile:
    """Replace a unique occurrence of old_string with new_string in a workspace file."""

    name: ClassVar[str] = "edit_file"
    description: ClassVar[str] = (
        "Replace a unique occurrence of old_string with new_string in a file. "
        "Fails if old_string is not found or matches more than once."
    )
    arguments_schema: ClassVar[dict[str, Any]] = EditFileArgs.model_json_schema()

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,
    ) -> ToolResult:
        validated = EditFileArgs.model_validate(args)
        workspace_root = workspace.path.resolve()
        target = (workspace.path / validated.path).resolve()

        if not target.is_relative_to(workspace_root):
            raise ToolError(f"edit_file: path '{validated.path}' is outside the workspace")
        if not target.exists():
            raise ToolError(f"edit_file: '{validated.path}' not found")
        if not target.is_file():
            raise ToolError(f"edit_file: '{validated.path}' is not a regular file")

        start = time.monotonic()
        original_bytes = target.read_bytes()
        content = original_bytes.decode("utf-8", errors="replace")

        count = content.count(validated.old_string)
        if count == 0:
            raise ToolError(f"edit_file: old_string not found in '{validated.path}'")
        if count > 1:
            raise ToolError(
                f"edit_file: old_string matched {count} times in '{validated.path}'; "
                "provide more context to make it unique"
            )

        new_content = content.replace(validated.old_string, validated.new_string, 1)
        new_bytes = new_content.encode("utf-8")
        target.write_bytes(new_bytes)
        latency = int((time.monotonic() - start) * 1000)

        return ToolResult(
            name=self.name,
            ok=True,
            output=f"edit_file: replaced 1 occurrence in '{validated.path}'",
            metadata={
                "path": str(validated.path),
                "occurrences": 1,
                "bytes_diff": len(new_bytes) - len(original_bytes),
            },
            latency_ms=latency,
        )
