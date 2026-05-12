from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable


class ToolError(RuntimeError):
    """Raised when a tool cannot fulfil its contract.

    The loop converts these into a ``tool_result`` with status=error so
    the LLM can recover. Tools themselves should always raise (not return
    error sentinels) so the loop has a single failure path.
    """


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation issued by the LLM."""

    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Outcome of a tool invocation.

    The runner applies redactor.redact() to *output* and serialises
    *metadata* before persisting an AgentStep row.
    """

    name: str
    ok: bool
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0


@dataclass(frozen=True)
class WorkspaceContext:
    """Minimal duck-typed shape the tools need from the workspace.

    Decoupled from backend.agents.workspace.WorkspaceInfo so this package
    doesn't import that module. The runner constructs a WorkspaceContext
    from a real WorkspaceInfo when invoking tools.
    """

    path: Path  # repo root on disk
    head_sha: str


@runtime_checkable
class Tool(Protocol):
    """Single-method protocol every concrete tool implements."""

    name: ClassVar[str]
    description: ClassVar[str]
    arguments_schema: ClassVar[dict[str, Any]]

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,  # PlatformProvider; typed as Any to avoid heavy import here
    ) -> ToolResult: ...


async def _run_subprocess(
    cmd: list[str],
    cwd: Path,
    timeout_seconds: int,
    max_output_bytes: int,
) -> tuple[int, str, str, int]:
    """Run *cmd* as a subprocess and return (exit_code, stdout, stderr, latency_ms).

    Uses ``asyncio.create_subprocess_exec`` (no shell). The environment is
    scrubbed to only contain ``PATH``, ``LANG``, and ``HOME``. Stdout and
    stderr are each capped at *max_output_bytes*; bytes beyond that limit are
    silently dropped.

    Args:
        cmd: Argument vector; the first element is the binary.
        cwd: Working directory for the subprocess.
        timeout_seconds: Wall-clock time limit. Raises :class:`ToolError` on expiry.
        max_output_bytes: Per-stream byte cap; output beyond this is truncated.

    Returns:
        A 4-tuple of (exit_code, stdout_text, stderr_text, latency_ms).

    Raises:
        ToolError: If the process times out.
    """
    scrubbed_env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "HOME"}}

    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=scrubbed_env,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ToolError(
            f"run_command: process '{cmd[0]}' timed out after {timeout_seconds}s"
        ) from exc

    latency_ms = int((time.monotonic() - start) * 1000)

    if len(stdout_bytes) > max_output_bytes:
        stdout_bytes = stdout_bytes[:max_output_bytes]
    if len(stderr_bytes) > max_output_bytes:
        stderr_bytes = stderr_bytes[:max_output_bytes]

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    exit_code = proc.returncode if proc.returncode is not None else -1

    return exit_code, stdout_text, stderr_text, latency_ms
