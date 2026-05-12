"""Tests for backend.agents.workspace — open_workspace context manager.

Test strategy
-------------
- Happy-path and cleanup tests use a real local git fixture repo (session-scoped).
- All other tests use mocks to avoid network access and to exercise error paths
  deterministically.
- The git fixture uses ``file://`` URLs; the test helper passes
  ``allow_protocols=("file",)`` to bypass the https-only default.
- All tests are skipped automatically when ``git`` is not on ``PATH``.
"""

from __future__ import annotations

import asyncio
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.workspace import (
    WorkspaceError,
    WorkspaceInfo,
    _build_git_clone_cmd,
    _build_subprocess_env,
    _dir_size_bytes,
    _write_askpass_script,
    open_workspace,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git not found on PATH",
)


# ---------------------------------------------------------------------------
# Session-scoped fixture: tiny local bare repo
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def fixture_bare_repo() -> Iterator[Path]:
    """Create a small local bare git repo and yield its filesystem path.

    The fixture initialises a bare repo, makes a single commit on ``main``,
    and yields the path to the bare repo directory.  Tests clone from this
    path using a ``file://`` URL so no network access is required.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        bare = Path(tmpdir) / "bare.git"
        work = Path(tmpdir) / "work"

        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(bare)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(work)],
            check=True,
            capture_output=True,
        )
        (work / "README.md").write_text("# fixture\n")
        subprocess.run(["git", "-C", str(work), "add", "."], check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(work),
                "-c",
                "user.email=test@example.com",
                "-c",
                "user.name=Test",
                "commit",
                "-m",
                "init",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(work), "remote", "add", "origin", str(bare)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(work), "push", "origin", "main:main"],
            check=True,
            capture_output=True,
        )
        yield bare


# ---------------------------------------------------------------------------
# Happy-path tests (real git fixture)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_yields_workspace_info(fixture_bare_repo: Path) -> None:
    """open_workspace yields a WorkspaceInfo with expected fields."""
    clone_url = f"file://{fixture_bare_repo}"
    async with open_workspace(
        clone_url=clone_url,
        branch="main",
        repo_external_id="test/fixture",
        allow_protocols=("file",),
    ) as info:
        assert isinstance(info, WorkspaceInfo)
        assert info.path.exists()
        assert info.branch == "main"
        assert info.bytes_on_disk > 0
        assert info.repo_external_id == "test/fixture"


@pytest.mark.asyncio
async def test_head_sha_is_40_hex_chars(fixture_bare_repo: Path) -> None:
    """head_sha returned by open_workspace is a 40-character hex string."""
    clone_url = f"file://{fixture_bare_repo}"
    async with open_workspace(
        clone_url=clone_url,
        branch="main",
        repo_external_id="test/fixture",
        allow_protocols=("file",),
    ) as info:
        assert len(info.head_sha) == 40
        assert all(c in "0123456789abcdef" for c in info.head_sha)


@pytest.mark.asyncio
async def test_head_sha_matches_git_rev_parse(fixture_bare_repo: Path) -> None:
    """head_sha in WorkspaceInfo matches what git rev-parse HEAD returns externally."""
    clone_url = f"file://{fixture_bare_repo}"
    async with open_workspace(
        clone_url=clone_url,
        branch="main",
        repo_external_id="test/fixture",
        allow_protocols=("file",),
    ) as info:
        result = subprocess.run(
            ["git", "-C", str(info.path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        expected_sha = result.stdout.strip()
        assert info.head_sha == expected_sha


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_on_success(fixture_bare_repo: Path) -> None:
    """Temp directory is removed after a successful context exit."""
    clone_url = f"file://{fixture_bare_repo}"
    captured_path: Path | None = None
    async with open_workspace(
        clone_url=clone_url,
        branch="main",
        repo_external_id="test/fixture",
        allow_protocols=("file",),
    ) as info:
        captured_path = info.path

    assert captured_path is not None
    # The parent tempdir (one level up from "repo") should be gone.
    assert not captured_path.parent.exists()


@pytest.mark.asyncio
async def test_cleanup_on_exception(fixture_bare_repo: Path) -> None:
    """Temp directory is removed even when the caller raises inside the context."""
    clone_url = f"file://{fixture_bare_repo}"
    captured_path: Path | None = None

    with pytest.raises(RuntimeError, match="deliberate"):
        async with open_workspace(
            clone_url=clone_url,
            branch="main",
            repo_external_id="test/fixture",
            allow_protocols=("file",),
        ) as info:
            captured_path = info.path
            raise RuntimeError("deliberate")

    assert captured_path is not None
    assert not captured_path.parent.exists()


# ---------------------------------------------------------------------------
# Timeout test (mocked subprocess)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clone_timeout_raises_workspace_error() -> None:
    """WorkspaceError is raised when the clone exceeds timeout_seconds."""

    class _NeverCompletes:
        """Fake process whose communicate() stalls indefinitely."""

        returncode: int | None = None

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(9999)
            return b"", b""  # pragma: no cover

        def kill(self) -> None:
            pass

        async def wait(self) -> int:
            return -9

    async def _fake_create(*args: Any, **kwargs: Any) -> _NeverCompletes:
        return _NeverCompletes()

    with patch("backend.agents.workspace.asyncio.create_subprocess_exec", side_effect=_fake_create):
        with pytest.raises(WorkspaceError, match="timed out after 1s"):
            async with open_workspace(
                clone_url="https://example.com/repo.git",
                branch="main",
                repo_external_id="example/repo",
                timeout_seconds=1,
            ):
                pass  # pragma: no cover


@pytest.mark.asyncio
async def test_clone_timeout_kills_process() -> None:
    """The subprocess is killed when the clone times out."""
    kill_called = False

    class _NeverCompletes:
        returncode: int | None = None

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(9999)
            return b"", b""  # pragma: no cover

        def kill(self) -> None:
            nonlocal kill_called
            kill_called = True

        async def wait(self) -> int:
            return -9

    async def _fake_create(*args: Any, **kwargs: Any) -> _NeverCompletes:
        return _NeverCompletes()

    with patch("backend.agents.workspace.asyncio.create_subprocess_exec", side_effect=_fake_create):
        with pytest.raises(WorkspaceError, match="timed out"):
            async with open_workspace(
                clone_url="https://example.com/repo.git",
                branch="main",
                repo_external_id="example/repo",
                timeout_seconds=1,
            ):
                pass  # pragma: no cover

    assert kill_called, "proc.kill() must be called on timeout"


# ---------------------------------------------------------------------------
# Size cap test (mocked _dir_size_bytes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_size_cap_raises_before_yielding(fixture_bare_repo: Path) -> None:
    """WorkspaceError with 'exceeds cap' is raised when repo is over max_bytes."""
    clone_url = f"file://{fixture_bare_repo}"

    with patch(
        "backend.agents.workspace._dir_size_bytes",
        return_value=600 * 1024 * 1024,  # 600 MB
    ):
        with pytest.raises(WorkspaceError, match="exceeds cap"):
            async with open_workspace(
                clone_url=clone_url,
                branch="main",
                repo_external_id="test/fixture",
                max_bytes=500 * 1024 * 1024,
                allow_protocols=("file",),
            ):
                pass  # pragma: no cover — should never be reached


# ---------------------------------------------------------------------------
# Credential helper tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_credential_helper_sets_git_askpass(fixture_bare_repo: Path) -> None:
    """GIT_ASKPASS env var is set when credential_helper is provided."""
    env_seen: dict[str, str] | None = None

    # Intercept _run_clone to capture the env dict, then proceed normally.
    original_run_clone = __import__("backend.agents.workspace", fromlist=["_run_clone"])._run_clone

    async def _capture_run_clone(
        *,
        cmd: list[str],
        env: dict[str, str],
        cwd: Path,
        timeout_seconds: int,
    ) -> None:
        nonlocal env_seen
        env_seen = dict(env)
        await original_run_clone(cmd=cmd, env=env, cwd=cwd, timeout_seconds=timeout_seconds)

    with patch("backend.agents.workspace._run_clone", side_effect=_capture_run_clone):
        async with open_workspace(
            clone_url=f"file://{fixture_bare_repo}",
            branch="main",
            repo_external_id="test/fixture",
            credential_helper=lambda: "fake-token",
            allow_protocols=("file",),
        ):
            pass

    assert env_seen is not None
    assert "GIT_ASKPASS" in env_seen
    askpass_path = Path(env_seen["GIT_ASKPASS"])
    # Note: the file is cleaned up after context exit; we can only inspect the path string.
    assert "bps-git-askpass" in askpass_path.name


@pytest.mark.asyncio
async def test_credential_helper_askpass_script_properties(fixture_bare_repo: Path) -> None:
    """The GIT_ASKPASS script exists, has mode 0o700, and contains printf of BPS_TOKEN."""
    script_path_seen: Path | None = None
    script_content_seen: str | None = None
    script_mode_seen: int | None = None

    original_run_clone = __import__("backend.agents.workspace", fromlist=["_run_clone"])._run_clone

    async def _inspect_run_clone(
        *,
        cmd: list[str],
        env: dict[str, str],
        cwd: Path,
        timeout_seconds: int,
    ) -> None:
        nonlocal script_path_seen, script_content_seen, script_mode_seen
        if "GIT_ASKPASS" in env:
            sp = Path(env["GIT_ASKPASS"])
            if sp.exists():
                script_path_seen = sp
                script_content_seen = sp.read_text()
                script_mode_seen = stat.S_IMODE(sp.stat().st_mode)
        await original_run_clone(cmd=cmd, env=env, cwd=cwd, timeout_seconds=timeout_seconds)

    with patch("backend.agents.workspace._run_clone", side_effect=_inspect_run_clone):
        async with open_workspace(
            clone_url=f"file://{fixture_bare_repo}",
            branch="main",
            repo_external_id="test/fixture",
            credential_helper=lambda: "fake-token",
            allow_protocols=("file",),
        ):
            pass

    assert script_path_seen is not None, "askpass script was not created"
    assert script_content_seen is not None
    assert "printf" in script_content_seen
    assert "BPS_TOKEN" in script_content_seen
    assert script_mode_seen == 0o700


# ---------------------------------------------------------------------------
# Env scrubbing test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_env_scrubbing_excludes_parent_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Subprocess env never contains parent-process secrets."""
    monkeypatch.setenv("SHOULD_NOT_LEAK", "super-secret-value")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "also-secret")

    env_seen: dict[str, str] | None = None

    async def _fake_create(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal env_seen
        env_seen = kwargs.get("env", {})
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    # Also mock _resolve_head_sha so we don't need a real clone.
    with (
        patch("backend.agents.workspace.asyncio.create_subprocess_exec", side_effect=_fake_create),
        patch(
            "backend.agents.workspace._resolve_head_sha",
            new=AsyncMock(return_value="a" * 40),
        ),
        patch("backend.agents.workspace._dir_size_bytes", return_value=100),
    ):
        async with open_workspace(
            clone_url="https://example.com/repo.git",
            branch="main",
            repo_external_id="example/repo",
        ):
            pass

    assert env_seen is not None
    # Required keys must be present.
    for key in ("PATH", "LANG", "HOME", "GIT_TERMINAL_PROMPT", "GIT_CONFIG_NOSYSTEM"):
        assert key in env_seen, f"Expected {key!r} in subprocess env"
    # Leaked secrets must NOT be present.
    assert "SHOULD_NOT_LEAK" not in env_seen
    assert "AWS_SECRET_ACCESS_KEY" not in env_seen


@pytest.mark.asyncio
async def test_env_scrubbing_with_credential_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a credential_helper, env also contains GIT_ASKPASS and BPS_TOKEN."""
    monkeypatch.setenv("RUNNER_SECRET", "runner-token")

    env_seen: dict[str, str] | None = None

    async def _fake_create(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal env_seen
        env_seen = kwargs.get("env", {})
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    with (
        patch("backend.agents.workspace.asyncio.create_subprocess_exec", side_effect=_fake_create),
        patch(
            "backend.agents.workspace._resolve_head_sha",
            new=AsyncMock(return_value="b" * 40),
        ),
        patch("backend.agents.workspace._dir_size_bytes", return_value=100),
    ):
        async with open_workspace(
            clone_url="https://example.com/repo.git",
            branch="main",
            repo_external_id="example/repo",
            credential_helper=lambda: "pat-value",
        ):
            pass

    assert env_seen is not None
    assert "GIT_ASKPASS" in env_seen
    assert "BPS_TOKEN" in env_seen
    assert "RUNNER_SECRET" not in env_seen


# ---------------------------------------------------------------------------
# _build_git_clone_cmd tests
# ---------------------------------------------------------------------------


def test_build_git_clone_cmd_blocks_dangerous_protocols() -> None:
    """Dangerous protocols are explicitly set to 'never' in the clone command."""
    cmd = _build_git_clone_cmd(
        clone_url="https://example.com/repo.git",
        branch="main",
        depth=50,
        target="/tmp/test-target",
    )
    # Check dangerous protocols are blocked.
    for proto in ("file", "ext", "ssh"):
        assert ["-c", f"protocol.{proto}.allow=never"] in [
            cmd[i : i + 2] for i in range(len(cmd) - 1)
        ], f"protocol.{proto}.allow=never not found in cmd"


def test_build_git_clone_cmd_allows_https_by_default() -> None:
    """HTTPS is allowed in the default clone command."""
    cmd = _build_git_clone_cmd(
        clone_url="https://example.com/repo.git",
        branch="main",
        depth=50,
        target="/tmp/test-target",
    )
    assert ["-c", "protocol.https.allow=always"] in [cmd[i : i + 2] for i in range(len(cmd) - 1)]


def test_build_git_clone_cmd_no_shell_metacharacters() -> None:
    """No shell metacharacters appear in the argument list."""
    cmd = _build_git_clone_cmd(
        clone_url="https://example.com/repo.git",
        branch="main",
        depth=50,
        target="/tmp/test-target",
    )
    bad_chars = set("|;&$`<>\\")
    for arg in cmd:
        found = bad_chars.intersection(arg)
        # Tildes and slashes in paths are OK; only real metacharacters are checked.
        assert not found, f"Metacharacter(s) {found!r} found in arg {arg!r}"


def test_build_git_clone_cmd_no_dangerous_flags() -> None:
    """Flags that could be abused (--shallow-since, --upload-pack) are absent."""
    cmd = _build_git_clone_cmd(
        clone_url="https://example.com/repo.git",
        branch="main",
        depth=50,
        target="/tmp/test-target",
    )
    cmd_str = " ".join(cmd)
    assert "--shallow-since" not in cmd_str
    assert "--upload-pack" not in cmd_str


def test_build_git_clone_cmd_includes_depth_and_single_branch() -> None:
    """depth and --single-branch flags are present in the command."""
    cmd = _build_git_clone_cmd(
        clone_url="https://example.com/repo.git",
        branch="feature",
        depth=10,
        target="/tmp/out",
    )
    assert "--depth=10" in cmd
    assert "--single-branch" in cmd
    assert "--branch=feature" in cmd


def test_build_git_clone_cmd_blanks_credential_helper() -> None:
    """credential.helper is blanked to prevent system config injection."""
    cmd = _build_git_clone_cmd(
        clone_url="https://example.com/repo.git",
        branch="main",
        depth=50,
        target="/tmp/test-target",
    )
    pairs = [cmd[i : i + 2] for i in range(len(cmd) - 1)]
    assert ["-c", "credential.helper="] in pairs


# ---------------------------------------------------------------------------
# Non-zero exit code test (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clone_failure_raises_workspace_error_with_exit_code() -> None:
    """WorkspaceError includes exit code and truncated stderr on clone failure."""

    async def _fake_create(*args: Any, **kwargs: Any) -> MagicMock:
        proc = MagicMock()
        stderr_msg = b"fatal: Remote branch foo not found in upstream origin"
        proc.communicate = AsyncMock(return_value=(b"", stderr_msg))
        proc.returncode = 128
        return proc

    with patch("backend.agents.workspace.asyncio.create_subprocess_exec", side_effect=_fake_create):
        with pytest.raises(WorkspaceError, match="exit code 128"):
            async with open_workspace(
                clone_url="https://example.com/repo.git",
                branch="foo",
                repo_external_id="example/repo",
            ):
                pass  # pragma: no cover


@pytest.mark.asyncio
async def test_clone_failure_includes_stderr_in_error_message() -> None:
    """WorkspaceError message contains (truncated) git stderr output."""

    async def _fake_create(*args: Any, **kwargs: Any) -> MagicMock:
        proc = MagicMock()
        stderr_msg = b"fatal: Remote branch foo not found in upstream origin"
        proc.communicate = AsyncMock(return_value=(b"", stderr_msg))
        proc.returncode = 128
        return proc

    with patch("backend.agents.workspace.asyncio.create_subprocess_exec", side_effect=_fake_create):
        with pytest.raises(WorkspaceError, match="Remote branch foo not found"):
            async with open_workspace(
                clone_url="https://example.com/repo.git",
                branch="foo",
                repo_external_id="example/repo",
            ):
                pass  # pragma: no cover


# ---------------------------------------------------------------------------
# _build_subprocess_env unit test
# ---------------------------------------------------------------------------


def test_build_subprocess_env_keys(tmp_path: Path) -> None:
    """_build_subprocess_env returns exactly the expected keys."""
    env = _build_subprocess_env(tmp_path, None)
    assert set(env) == {"PATH", "LANG", "HOME", "GIT_TERMINAL_PROMPT", "GIT_CONFIG_NOSYSTEM"}


def test_build_subprocess_env_home_is_tmpdir(tmp_path: Path) -> None:
    """HOME in the subprocess env points to the provided tmpdir."""
    env = _build_subprocess_env(tmp_path, None)
    assert env["HOME"] == str(tmp_path)


def test_build_subprocess_env_terminal_prompt_disabled(tmp_path: Path) -> None:
    """GIT_TERMINAL_PROMPT is '0' so git never prompts interactively."""
    env = _build_subprocess_env(tmp_path, None)
    assert env["GIT_TERMINAL_PROMPT"] == "0"


# ---------------------------------------------------------------------------
# _write_askpass_script unit tests
# ---------------------------------------------------------------------------


def test_write_askpass_script_mode(tmp_path: Path) -> None:
    """askpass script has mode 0o700."""
    script = _write_askpass_script(tmp_path)
    assert stat.S_IMODE(script.stat().st_mode) == 0o700


def test_write_askpass_script_content(tmp_path: Path) -> None:
    """askpass script prints $BPS_TOKEN via printf."""
    script = _write_askpass_script(tmp_path)
    content = script.read_text()
    assert "printf" in content
    assert "BPS_TOKEN" in content


# ---------------------------------------------------------------------------
# _dir_size_bytes unit test
# ---------------------------------------------------------------------------


def test_dir_size_bytes_counts_files(tmp_path: Path) -> None:
    """_dir_size_bytes sums sizes of all regular files recursively."""
    (tmp_path / "a.txt").write_bytes(b"x" * 100)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_bytes(b"y" * 200)
    assert _dir_size_bytes(tmp_path) == 300
