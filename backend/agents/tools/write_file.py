from __future__ import annotations

import time
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.agents.tools.base import ToolError, ToolResult, WorkspaceContext


class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Repository-relative path, no leading slash.")
    content: str = Field(..., description="Full text content to write to the file.")


class WriteFile:
    """Write content to a file inside the workspace (creates parent dirs if needed)."""

    name: ClassVar[str] = "write_file"
    description: ClassVar[str] = (
        "Write content to a file inside the workspace. "
        "Parent directories are created automatically. "
        "Content is capped at 1 MB."
    )
    arguments_schema: ClassVar[dict[str, Any]] = WriteFileArgs.model_json_schema()

    _MAX_BYTES: ClassVar[int] = 1024 * 1024  # 1 MB

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,
    ) -> ToolResult:
        validated = WriteFileArgs.model_validate(args)
        workspace_root = workspace.path.resolve()
        target = (workspace.path / validated.path).resolve()

        if not target.is_relative_to(workspace_root):
            raise ToolError(f"write_file: path '{validated.path}' is outside the workspace")

        encoded = validated.content.encode("utf-8")
        if len(encoded) > self._MAX_BYTES:
            raise ToolError(
                f"write_file: content exceeds 1 MB cap ({len(encoded)} bytes > {self._MAX_BYTES})"
            )

        created = not target.exists()

        start = time.monotonic()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        latency = int((time.monotonic() - start) * 1000)

        return ToolResult(
            name=self.name,
            ok=True,
            output=f"write_file: wrote {len(encoded)} bytes to '{validated.path}'",
            metadata={
                "path": str(validated.path),
                "bytes_written": len(encoded),
                "created": created,
            },
            latency_ms=latency,
        )
