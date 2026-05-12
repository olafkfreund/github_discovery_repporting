from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.agents.tools.base import ToolError, ToolResult, WorkspaceContext, _run_subprocess

_MAX_OUTPUT_BYTES = 64 * 1024


class GitDiffArgs(BaseModel):
    rev_a: str | None = Field(
        None,
        description="Starting revision (commit SHA, branch, or tag). Omit for an unstaged diff.",
    )
    rev_b: str | None = Field(
        None,
        description="Ending revision. Required if rev_a is provided.",
    )


class GitDiff:
    """Show a git diff for the workspace, optionally between two revisions."""

    name: ClassVar[str] = "git_diff"
    description: ClassVar[str] = (
        "Show a git diff for the workspace. "
        "Pass rev_a and rev_b to diff between two commits/branches."
    )
    arguments_schema: ClassVar[dict[str, Any]] = GitDiffArgs.model_json_schema()

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,
    ) -> ToolResult:
        validated = GitDiffArgs.model_validate(args)

        cmd: list[str] = ["git", "diff"]
        if validated.rev_a is not None:
            cmd.append(validated.rev_a)
        if validated.rev_b is not None:
            if validated.rev_a is None:
                raise ToolError("git_diff: rev_b requires rev_a to also be set")
            cmd.append(validated.rev_b)

        exit_code, stdout, stderr, latency = await _run_subprocess(
            cmd=cmd,
            cwd=workspace.path,
            timeout_seconds=30,
            max_output_bytes=_MAX_OUTPUT_BYTES,
        )

        ok = exit_code == 0
        return ToolResult(
            name=self.name,
            ok=ok,
            output=stdout if ok else f"git diff failed (exit {exit_code}):\n{stderr}",
            metadata={
                "exit_code": exit_code,
                "rev_a": validated.rev_a,
                "rev_b": validated.rev_b,
            },
            latency_ms=latency,
        )
