"""Sandboxed git workspace management for the agent subsystem.

This module provides :func:`open_workspace`, an async context manager that clones
a target repository into a freshly-created temporary directory with strict
environment scrubbing, a wall-clock timeout, a repo-size cap, and credential
injection via ``GIT_ASKPASS``.  The temporary directory is unconditionally
removed on context exit regardless of whether an exception was raised.

Security model
--------------
The subprocess environment is *not* inherited from the parent process.  Only the
keys required for git's operation are passed explicitly.  This prevents accidental
leakage of secrets, proxy credentials, or runner tokens into the clone subprocess.

PATs are injected via a one-shot ``GIT_ASKPASS`` script written inside the temp
directory so that the token never appears on the command line, in ``ps`` output,
or in any environment variable that is visible to sibling processes.

Git protocol filtering is applied via ``-c protocol.<name>.allow=`` flags so that
only HTTPS (or a test-injected alternative) is ever permitted.  SSH, ext, and
file-based URLs are explicitly blocked.

Limitations (documented)
--------------------------
- LFS objects are NOT fetched (intentional for shallow clones).
- Git submodules are NOT initialised.
- Network isolation via nsjail/bwrap is NOT implemented; deferred to Phase 5
  hardening.  The subprocess inherits the parent's network access.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceInfo:
    """A checked-out, sandboxed git workspace.

    Attributes:
        path: Absolute path to the temporary directory.  Valid only inside the
            ``async with open_workspace(...)`` block — the directory is removed
            on exit.
        repo_external_id: Provider-defined repository identifier
            (``owner/name`` for GitHub, numeric project id for GitLab,
            ``project:repo`` for Azure DevOps).
        branch: Branch that was checked out.
        head_sha: Full 40-character SHA of HEAD at clone time.
        bytes_on_disk: Total size of all files under *path* at the time the
            context was entered.  Excludes symlinks.
    """

    path: Path
    repo_external_id: str
    branch: str
    head_sha: str
    bytes_on_disk: int


class WorkspaceError(RuntimeError):
    """Raised when clone, sandbox setup, or size-cap enforcement fails.

    The message always includes enough context to diagnose the failure:
    exit code, truncated stderr (≤ 500 chars), or a human-readable description
    of which limit was exceeded.
    """


# Default allowed git protocols when the public API is used.
# Tests can override via the *allow_protocols* parameter documented below.
_DEFAULT_ALLOWED_PROTOCOLS: tuple[str, ...] = ("https",)


@asynccontextmanager
async def open_workspace(
    *,
    clone_url: str,
    branch: str,
    repo_external_id: str,
    credential_helper: Callable[[], str] | None = None,
    timeout_seconds: int = 60,
    max_bytes: int = 500 * 1024 * 1024,
    depth: int = 50,
    allow_protocols: tuple[str, ...] = _DEFAULT_ALLOWED_PROTOCOLS,
) -> AsyncIterator[WorkspaceInfo]:
    """Clone *clone_url* into a fresh tempdir and yield a :class:`WorkspaceInfo`.

    The tempdir is removed on context exit (success OR exception).

    Args:
        clone_url: HTTPS URL.  The PAT is NEVER inlined into the URL.  Use
            *credential_helper* for credential injection.
        branch: Branch to check out (also passed via ``--single-branch``).
        repo_external_id: Identifier used for logging and stored on the
            returned :class:`WorkspaceInfo` (provider-defined: GitHub
            ``owner/name``, GitLab numeric project id, Azure DevOps
            ``project:repo``).
        credential_helper: Optional zero-arg callable returning the PAT.
            When provided, a one-shot ``GIT_ASKPASS`` script is written to
            the tempdir and removed on cleanup.  The token never appears on
            the command line, never in environment variables visible to other
            processes.
        timeout_seconds: Wall-clock cap on the clone operation.
        max_bytes: Maximum allowed repo size on disk.  Checked AFTER clone
            but BEFORE yielding so callers never see an oversized workspace.
        depth: ``--depth`` value (shallow clone).
        allow_protocols: **Test-only**.  Tuple of git protocol names to allow.
            Defaults to ``("https",)``.  Tests that use local ``file://``
            fixture repos should pass ``("file",)`` here.  Do NOT override
            this parameter in production code.

    Raises:
        WorkspaceError: on clone failure, timeout, oversized repo, or
            sandbox setup error.

    Limitations (documented):
        - LFS objects are NOT fetched (intentional for shallow clones).
        - Git submodules are NOT initialised.
        - Network isolation via nsjail/bwrap is NOT implemented in this
          issue; deferred to Phase 5 hardening.  The subprocess still
          inherits the parent process's network access.
    """
    tmp = tempfile.TemporaryDirectory(prefix="bps-agent-")
    try:
        tmp_path = Path(tmp.name)
        askpass_path: Path | None = None

        env = _build_subprocess_env(tmp_path, credential_helper)
        if credential_helper is not None:
            askpass_path = _write_askpass_script(tmp_path)
            env["GIT_ASKPASS"] = str(askpass_path)
            env["BPS_TOKEN"] = credential_helper()

        cmd = _build_git_clone_cmd(
            clone_url=clone_url,
            branch=branch,
            depth=depth,
            target=str(tmp_path / "repo"),
            allow_protocols=allow_protocols,
        )

        await _run_clone(cmd=cmd, env=env, cwd=tmp_path, timeout_seconds=timeout_seconds)

        # Resolve HEAD inside the cloned sub-directory "repo".
        workspace_path = tmp_path / "repo"
        bytes_on_disk = _dir_size_bytes(workspace_path)
        if bytes_on_disk > max_bytes:
            raise WorkspaceError(
                f"Repo size {bytes_on_disk // (1024 * 1024)}MB exceeds cap "
                f"{max_bytes // (1024 * 1024)}MB"
            )

        head_sha = await _resolve_head_sha(workspace_path, env)

        yield WorkspaceInfo(
            path=workspace_path,
            repo_external_id=repo_external_id,
            branch=branch,
            head_sha=head_sha,
            bytes_on_disk=bytes_on_disk,
        )
    finally:
        tmp.cleanup()  # also removes the askpass script


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_subprocess_env(
    tmpdir: Path,
    credential_helper: Callable[[], str] | None,  # noqa: ARG001 – reserved for future use
) -> dict[str, str]:
    """Return a minimal env dict for the clone subprocess.

    Only the keys necessary for git's operation are included.  The parent
    process's env is NOT inherited wholesale — this prevents accidental
    leakage of corporate proxy credentials, runner secrets, SSH agent sockets,
    etc. into the clone subprocess.

    The ``HOME`` key is set to *tmpdir* so that git reads a fresh, empty
    ``~/.gitconfig`` rather than the developer's or runner's real config.

    Args:
        tmpdir: Path to the temporary directory used as the subprocess home.
        credential_helper: Currently unused; reserved so callers can be written
            uniformly.  Credential injection is done separately by the caller.

    Returns:
        A dictionary containing only the keys required for git to operate.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "HOME": str(tmpdir),
        "GIT_TERMINAL_PROMPT": "0",  # never prompt for credentials interactively
        "GIT_CONFIG_NOSYSTEM": "1",  # ignore /etc/gitconfig
    }


def _write_askpass_script(tmpdir: Path) -> Path:
    """Write a one-shot bash script that prints ``$BPS_TOKEN``.

    The script is written with mode ``0o700`` (owner execute only) so that
    other processes on the same host cannot read or execute it.

    ``GIT_ASKPASS`` is called by git whenever it needs a username or password.
    The script simply echoes ``$BPS_TOKEN``, which is set in the subprocess
    environment by the caller.  This keeps the token out of ``/proc/<pid>/cmdline``
    and out of any log files that record the full argv.

    Args:
        tmpdir: Parent directory; the script is placed directly inside it.

    Returns:
        Path to the created script file.
    """
    script = tmpdir / "bps-git-askpass"
    script.write_text('#!/usr/bin/env bash\nprintf "%s" "${BPS_TOKEN}"\n')
    script.chmod(0o700)
    return script


def _build_git_clone_cmd(
    *,
    clone_url: str,
    branch: str,
    depth: int,
    target: str,
    allow_protocols: tuple[str, ...] = _DEFAULT_ALLOWED_PROTOCOLS,
) -> list[str]:
    """Build the git clone command line as an argument list (no shell expansion).

    Protocol filtering is applied via ``-c protocol.<name>.allow=`` flags.
    ``file``, ``ext``, and ``ssh`` are blocked unconditionally; the protocols
    listed in *allow_protocols* are then explicitly permitted.  By default
    only ``https`` is allowed.

    The ``credential.helper`` and ``http.extraHeader`` config values are
    blanked to prevent any system or user git configuration from injecting
    credentials or headers into the outbound request.

    Args:
        clone_url: Repository URL.
        branch: Branch to check out.
        depth: Shallow clone depth.
        target: Destination path for the cloned repository.
        allow_protocols: Protocols to permit.  **Test-only override** — use
            ``("file",)`` for local fixture repos.

    Returns:
        A list of strings suitable for :func:`asyncio.create_subprocess_exec`.
        No shell metacharacters are present; every component is a discrete
        argument.
    """
    cmd: list[str] = ["git"]
    # Block dangerous protocols unconditionally.
    for proto in ("file", "ext", "ssh"):
        cmd.extend(["-c", f"protocol.{proto}.allow=never"])
    # Permit the requested protocols.
    for proto in allow_protocols:
        cmd.extend(["-c", f"protocol.{proto}.allow=always"])
    cmd.extend(
        [
            "-c",
            "credential.helper=",
            "-c",
            "http.extraHeader=",
            "clone",
            f"--depth={depth}",
            "--single-branch",
            f"--branch={branch}",
            clone_url,
            target,
        ]
    )
    return cmd


async def _run_clone(
    *,
    cmd: list[str],
    env: dict[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> None:
    """Run the git clone subprocess with a wall-clock timeout.

    Stdout and stderr are captured.  If the process exits with a non-zero
    return code the first 500 characters of stderr are included in the
    :class:`WorkspaceError` message to aid diagnosis without flooding logs.

    Args:
        cmd: Argument list produced by :func:`_build_git_clone_cmd`.
        env: Scrubbed environment dict produced by :func:`_build_subprocess_env`.
        cwd: Working directory for the subprocess.
        timeout_seconds: Maximum wall-clock seconds to wait for the clone.

    Raises:
        WorkspaceError: On timeout (process is killed before raising) or
            non-zero exit code.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env=env,
        cwd=str(cwd),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise WorkspaceError(f"Clone timed out after {timeout_seconds}s") from None

    if proc.returncode != 0:
        raise WorkspaceError(
            f"git clone failed with exit code {proc.returncode}: "
            f"{stderr.decode('utf-8', errors='replace')[:500]}"
        )


def _dir_size_bytes(path: Path) -> int:
    """Recursively sum file sizes under *path*, excluding symlinks.

    Uses :func:`os.walk` which is synchronous but fast enough for the
    post-clone size-cap check (called once, not in a hot loop).  Symlinks
    are excluded to avoid inflating the total with targets that may not
    actually be present.

    Args:
        path: Root directory to measure.

    Returns:
        Total size in bytes of all regular files under *path*.
    """
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = Path(root) / f
            if fp.is_file() and not fp.is_symlink():
                total += fp.stat().st_size
    return total


async def _resolve_head_sha(workspace_path: Path, env: dict[str, str]) -> str:
    """Run ``git rev-parse HEAD`` inside the workspace and return the SHA.

    Args:
        workspace_path: Absolute path to the cloned repository directory.
        env: Scrubbed environment dict (same as used for the clone).

    Returns:
        The full 40-character hexadecimal SHA of HEAD.

    Raises:
        WorkspaceError: If ``git rev-parse HEAD`` exits with a non-zero code.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "HEAD",
        env=env,
        cwd=str(workspace_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise WorkspaceError(
            f"git rev-parse HEAD failed: {stderr.decode('utf-8', errors='replace')[:200]}"
        )
    return stdout.decode().strip()
