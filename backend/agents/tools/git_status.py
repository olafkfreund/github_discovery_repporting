from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from backend.agents.tools.base import ToolResult, WorkspaceContext, _run_subprocess

_MAX_OUTPUT_BYTES = 32 * 1024


class GitStatusArgs(BaseModel):
    """No arguments — always shows the full porcelain status of the workspace."""


class GitStatus:
    """Show the working-tree status of the workspace (git status --porcelain=v1)."""

    name: ClassVar[str] = "git_status"
    description: ClassVar[str] = (
        "Show the working-tree status of the workspace using git status --porcelain=v1."
    )
    arguments_schema: ClassVar[dict[str, Any]] = GitStatusArgs.model_json_schema()

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,
    ) -> ToolResult:
        GitStatusArgs.model_validate(args)

        cmd = ["git", "status", "--porcelain=v1"]
        exit_code, stdout, stderr, latency = await _run_subprocess(
            cmd=cmd,
            cwd=workspace.path,
            timeout_seconds=15,
            max_output_bytes=_MAX_OUTPUT_BYTES,
        )

        ok = exit_code == 0
        return ToolResult(
            name=self.name,
            ok=ok,
            output=stdout if ok else f"git status failed (exit {exit_code}):\n{stderr}",
            metadata={"exit_code": exit_code},
            latency_ms=latency,
        )
