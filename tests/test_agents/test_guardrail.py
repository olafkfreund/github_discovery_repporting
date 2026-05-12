"""Tests for backend.agents.guardrail (REQ-061 diff-scope guardrail).

Strategy: mock ``_git_diff_name_only`` to avoid requiring a real git repo.
All edge cases for the allow-list / forbidden-list logic are exercised at the
``check_diff_scope`` level.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.guardrail import GuardrailViolation, _evidence_paths, check_diff_scope
from backend.agents.workspace import WorkspaceInfo
from backend.models.enums import Severity
from backend.remediation.recipe import RemediationRecipe

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _fake_workspace(tmp_path: Path) -> WorkspaceInfo:
    """Return a WorkspaceInfo pointing at *tmp_path*."""
    return WorkspaceInfo(
        path=tmp_path,
        repo_external_id="test-org/test-repo",
        branch="main",
        head_sha="a" * 40,
        bytes_on_disk=1024,
    )


def _fake_recipe(
    globs: list[str] | None = None,
    forbidden: list[str] | None = None,
) -> RemediationRecipe:
    """Return a minimal :class:`RemediationRecipe` for testing."""
    return RemediationRecipe(
        check_id="TEST-001",
        severity=Severity.medium,
        file_glob_hints=globs or [],
        forbidden_paths=forbidden or [],
    )


def _fake_finding(affected_paths: list[str] | None = None) -> SimpleNamespace:
    """Return a lightweight stand-in for a :class:`~backend.models.finding.Finding`.

    Only the ``evidence`` attribute is accessed by the guardrail functions, so
    we use :class:`~types.SimpleNamespace` to avoid SQLAlchemy ORM overhead.

    Args:
        affected_paths: Value to store under ``evidence["affected_paths"]``.
            Pass ``None`` to produce a finding with ``evidence=None``.

    Returns:
        A namespace with an ``evidence`` attribute.
    """
    evidence = {"affected_paths": affected_paths} if affected_paths is not None else None
    return SimpleNamespace(evidence=evidence)


# ---------------------------------------------------------------------------
# Tests: _evidence_paths helper
# ---------------------------------------------------------------------------


def test_evidence_paths_returns_empty_for_none_evidence() -> None:
    """Finding with evidence=None → empty list."""
    finding = _fake_finding()
    finding.evidence = None
    assert _evidence_paths(finding) == []


def test_evidence_paths_returns_empty_for_missing_key() -> None:
    """Finding with evidence={} (no affected_paths key) → empty list."""
    finding = _fake_finding()
    finding.evidence = {"other_key": "value"}
    assert _evidence_paths(finding) == []


def test_evidence_paths_returns_empty_for_non_list_value() -> None:
    """When affected_paths is not a list, return []."""
    finding = _fake_finding()
    finding.evidence = {"affected_paths": "src/foo.py"}  # string, not list
    assert _evidence_paths(finding) == []


def test_evidence_paths_strips_leading_slash() -> None:
    """Absolute paths in evidence are normalised to relative."""
    finding = _fake_finding()
    finding.evidence = {"affected_paths": ["/src/foo.py", "config/app.yaml"]}
    result = _evidence_paths(finding)
    assert "src/foo.py" in result
    assert "config/app.yaml" in result


def test_evidence_paths_drops_non_string_entries() -> None:
    """Non-string entries in affected_paths are silently dropped."""
    finding = _fake_finding()
    finding.evidence = {"affected_paths": ["src/foo.py", 42, None, "bar.py"]}
    result = _evidence_paths(finding)
    assert result == ["src/foo.py", "bar.py"]


# ---------------------------------------------------------------------------
# Tests: check_diff_scope — core allow/deny logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_files_inside_globs_returns_none(tmp_path: Path) -> None:
    """All changed files match the recipe globs → no violation."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["src/**"])
    finding = _fake_finding()

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=["src/foo.py", "src/bar.py"],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    assert result is None


@pytest.mark.asyncio
async def test_file_outside_globs_and_no_evidence_returns_violation(tmp_path: Path) -> None:
    """A file outside the globs with no evidence paths → violation listing the file."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["src/**"])
    finding = _fake_finding(affected_paths=[])

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=["docs/README.md"],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    assert result is not None
    assert isinstance(result, GuardrailViolation)
    assert "docs/README.md" in result.files_out_of_scope
    assert not result.files_in_forbidden_paths


@pytest.mark.asyncio
async def test_forbidden_path_blocked_even_inside_allowed_glob(tmp_path: Path) -> None:
    """A file matching a forbidden glob is rejected even when the allow-list also matches."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["**/*"], forbidden=[".github/**"])
    finding = _fake_finding()

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=[".github/workflows/ci.yml"],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    assert result is not None
    assert ".github/workflows/ci.yml" in result.files_in_forbidden_paths
    assert not result.files_out_of_scope


@pytest.mark.asyncio
async def test_empty_diff_returns_none(tmp_path: Path) -> None:
    """An empty diff (no changed files) always returns None."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["src/**"])
    finding = _fake_finding()

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    assert result is None


@pytest.mark.asyncio
async def test_no_allow_list_and_no_evidence_all_files_out_of_scope(tmp_path: Path) -> None:
    """When both globs and evidence are empty, changed files are all out-of-scope."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=[], forbidden=[])
    finding = _fake_finding(affected_paths=[])

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=["src/foo.py"],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    assert result is not None
    assert "src/foo.py" in result.files_out_of_scope
    assert result.allowed_globs == []
    assert result.cited_evidence_paths == []


@pytest.mark.asyncio
async def test_file_allowed_via_evidence_path(tmp_path: Path) -> None:
    """A file not matched by globs but present in evidence paths is allowed."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["src/**"])
    # evidence says config/app.yaml is affected
    finding = _fake_finding(affected_paths=["config/app.yaml"])

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=["src/foo.py", "config/app.yaml"],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    assert result is None


@pytest.mark.asyncio
async def test_mixed_in_scope_and_out_of_scope(tmp_path: Path) -> None:
    """Only the out-of-scope file appears in the violation; in-scope files are fine."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["src/**"])
    finding = _fake_finding(affected_paths=["config/app.yaml"])

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        # src/foo.py — matches glob
        # config/app.yaml — matches evidence
        # docs/guide.md — out of scope
        return_value=["src/foo.py", "config/app.yaml", "docs/guide.md"],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    assert result is not None
    assert result.files_out_of_scope == ["docs/guide.md"]
    assert "src/foo.py" not in result.files_out_of_scope
    assert "config/app.yaml" not in result.files_out_of_scope


@pytest.mark.asyncio
async def test_finding_without_evidence_dict(tmp_path: Path) -> None:
    """Finding.evidence is None → evidence_paths returns [] → no crash."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["src/**"])
    finding = _fake_finding()
    finding.evidence = None

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=["src/foo.py"],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    # src/foo.py matches the glob → should pass.
    assert result is None


@pytest.mark.asyncio
async def test_guardrail_violation_reason_forbidden(tmp_path: Path) -> None:
    """GuardrailViolation.reason leads with forbidden_paths_matched when relevant."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["**/*"], forbidden=["secrets/**"])
    finding = _fake_finding()

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=["secrets/prod.env"],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    assert result is not None
    assert result.reason.startswith("forbidden_paths_matched")


@pytest.mark.asyncio
async def test_guardrail_violation_reason_out_of_scope(tmp_path: Path) -> None:
    """GuardrailViolation.reason leads with diff_out_of_scope when no forbidden hit."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["src/**"])
    finding = _fake_finding(affected_paths=[])

    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=["docs/README.md"],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    assert result is not None
    assert result.reason.startswith("diff_out_of_scope")


@pytest.mark.asyncio
async def test_git_diff_failure_returns_empty_no_crash(tmp_path: Path) -> None:
    """When git diff exits non-zero, _git_diff_name_only returns [] and no violation fires."""
    ws = _fake_workspace(tmp_path)
    recipe = _fake_recipe(globs=["src/**"])
    finding = _fake_finding()

    # Simulate git failure by returning empty list (as the real helper does on error).
    with patch(
        "backend.agents.guardrail._git_diff_name_only",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await check_diff_scope(workspace=ws, recipe=recipe, finding=finding)

    # Empty diff → no violation.
    assert result is None
