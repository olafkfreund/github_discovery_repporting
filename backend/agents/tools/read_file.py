from __future__ import annotations

import time
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.agents.tools.base import ToolError, ToolResult, WorkspaceContext


class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Repository-relative path, no leading slash.")


class ReadFile:
    """Read up to 100 KB of a file from the workspace."""

    name: ClassVar[str] = "read_file"
    description: ClassVar[str] = "Read up to 100 KB of a file from the workspace."
    arguments_schema: ClassVar[dict[str, Any]] = ReadFileArgs.model_json_schema()

    _MAX_BYTES: ClassVar[int] = 100 * 1024

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,
    ) -> ToolResult:
        validated = ReadFileArgs.model_validate(args)
        workspace_root = workspace.path.resolve()
        target = (workspace.path / validated.path).resolve()

        if not target.is_relative_to(workspace_root):
            raise ToolError(f"read_file: path '{validated.path}' is outside the workspace")
        if not target.exists():
            raise ToolError(f"read_file: '{validated.path}' not found")
        if not target.is_file():
            raise ToolError(f"read_file: '{validated.path}' is not a regular file")

        start = time.monotonic()
        data = target.read_bytes()
        truncated = len(data) > self._MAX_BYTES
        if truncated:
            data = data[: self._MAX_BYTES]
        content = data.decode("utf-8", errors="replace")
        latency = int((time.monotonic() - start) * 1000)

        return ToolResult(
            name=self.name,
            ok=True,
            output=content + ("\n\n[TRUNCATED: file exceeded 100KB cap]" if truncated else ""),
            metadata={
                "path": str(validated.path),
                "bytes": len(data),
                "truncated": truncated,
            },
            latency_ms=latency,
        )
