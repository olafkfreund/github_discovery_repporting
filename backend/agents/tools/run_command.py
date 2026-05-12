from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.agents.tools.base import ToolError, ToolResult, WorkspaceContext, _run_subprocess


class RunCommandArgs(BaseModel):
    command: list[str] = Field(
        ...,
        min_length=1,
        description="Argv list; first element must be an allow-listed binary.",
    )
    timeout_seconds: int = Field(30, ge=1, le=300)


_MAX_OUTPUT_BYTES = 32 * 1024


class RunCommand:
    """Run an allow-listed command inside the workspace and return its output."""

    name: ClassVar[str] = "run_command"
    description: ClassVar[str] = (
        "Run an allow-listed command inside the workspace. "
        "Allowed binaries: git, pre-commit, ruff, yamllint, trivy, terraform."
    )
    arguments_schema: ClassVar[dict[str, Any]] = RunCommandArgs.model_json_schema()

    _ALLOWED_BINARIES: ClassVar[frozenset[str]] = frozenset(
        {
            "git",
            "pre-commit",
            "ruff",
            "yamllint",
            "trivy",
            "terraform",
        }
    )

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,
    ) -> ToolResult:
        validated = RunCommandArgs.model_validate(args)
        binary = validated.command[0]
        if binary not in self._ALLOWED_BINARIES:
            raise ToolError(
                f"run_command: binary '{binary}' is not allow-listed. "
                f"Allowed: {sorted(self._ALLOWED_BINARIES)}"
            )

        exit_code, stdout, stderr, latency = await _run_subprocess(
            cmd=validated.command,
            cwd=workspace.path,
            timeout_seconds=validated.timeout_seconds,
            max_output_bytes=_MAX_OUTPUT_BYTES,
        )

        ok = exit_code == 0
        output = (
            f"$ {' '.join(validated.command)}\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
        )
        return ToolResult(
            name=self.name,
            ok=ok,
            output=output,
            metadata={
                "exit_code": exit_code,
                "stdout_bytes": len(stdout.encode()),
                "stderr_bytes": len(stderr.encode()),
            },
            latency_ms=latency,
        )
