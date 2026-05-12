"""Tests for backend.remediation.success_checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.remediation.success_checks import (
    cicd001_success,
    cq004_success,
    repo001_success,
    repo008_success,
    secrets003_success,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _FakeWorkspace:
    """Minimal duck-typed workspace with a configurable path."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.head_sha = "abc123" * 6 + "ab"  # 40-char-ish

    @property
    def path(self) -> Path:
        return self._path


def _make_ctx(branch_protection=None) -> MagicMock:
    """Return a ProviderCtx-shaped mock with a configurable get_repo_assessment_data."""
    ctx = MagicMock()
    ctx.repo = MagicMock()

    assessment = MagicMock()
    assessment.branch_protection = branch_protection

    provider = AsyncMock()
    provider.get_repo_assessment_data = AsyncMock(return_value=assessment)
    ctx.provider = provider
    return ctx


# ---------------------------------------------------------------------------
# repo008_success
# ---------------------------------------------------------------------------


class TestRepo008Success:
    @pytest.mark.asyncio
    async def test_github_codeowners_path(self, tmp_path: Path) -> None:
        codeowners = tmp_path / ".github" / "CODEOWNERS"
        codeowners.parent.mkdir(parents=True)
        codeowners.write_text("* @security-team\n")
        ws = _FakeWorkspace(tmp_path)
        assert await repo008_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_root_codeowners_path(self, tmp_path: Path) -> None:
        (tmp_path / "CODEOWNERS").write_text("* @security-team\n")
        ws = _FakeWorkspace(tmp_path)
        assert await repo008_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_docs_codeowners_path(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "CODEOWNERS").write_text("* @security-team\n")
        ws = _FakeWorkspace(tmp_path)
        assert await repo008_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_no_codeowners_returns_false(self, tmp_path: Path) -> None:
        ws = _FakeWorkspace(tmp_path)
        assert await repo008_success(ws, _make_ctx()) is False


# ---------------------------------------------------------------------------
# secrets003_success
# ---------------------------------------------------------------------------


class TestSecrets003Success:
    @pytest.mark.asyncio
    async def test_valid_toml_returns_true(self, tmp_path: Path) -> None:
        (tmp_path / ".gitleaks.toml").write_text("[extend]\nuseDefault = true\n")
        ws = _FakeWorkspace(tmp_path)
        assert await secrets003_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_malformed_toml_returns_false(self, tmp_path: Path) -> None:
        (tmp_path / ".gitleaks.toml").write_text("this is not [ valid toml\n")
        ws = _FakeWorkspace(tmp_path)
        assert await secrets003_success(ws, _make_ctx()) is False

    @pytest.mark.asyncio
    async def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        ws = _FakeWorkspace(tmp_path)
        assert await secrets003_success(ws, _make_ctx()) is False


# ---------------------------------------------------------------------------
# cicd001_success
# ---------------------------------------------------------------------------


_VALID_CODEQL_YAML = """\
name: CodeQL
on:
  push:
    branches: [main]
jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""

_MALFORMED_YAML = "key: [unclosed bracket\n"


class TestCicd001Success:
    @pytest.mark.asyncio
    async def test_codeql_yml_returns_true(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "codeql.yml").write_text(_VALID_CODEQL_YAML)
        ws = _FakeWorkspace(tmp_path)
        assert await cicd001_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_codeql_yaml_extension(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "codeql.yaml").write_text(_VALID_CODEQL_YAML)
        ws = _FakeWorkspace(tmp_path)
        assert await cicd001_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_codeql_analysis_yml(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "codeql-analysis.yml").write_text(_VALID_CODEQL_YAML)
        ws = _FakeWorkspace(tmp_path)
        assert await cicd001_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_codeql_analysis_yaml_extension(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "codeql-analysis.yaml").write_text(_VALID_CODEQL_YAML)
        ws = _FakeWorkspace(tmp_path)
        assert await cicd001_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_malformed_yaml_returns_false(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "codeql.yml").write_text(_MALFORMED_YAML)
        ws = _FakeWorkspace(tmp_path)
        assert await cicd001_success(ws, _make_ctx()) is False

    @pytest.mark.asyncio
    async def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        ws = _FakeWorkspace(tmp_path)
        assert await cicd001_success(ws, _make_ctx()) is False


# ---------------------------------------------------------------------------
# cq004_success
# ---------------------------------------------------------------------------


_VALID_COVERAGE_YAML = """\
name: Coverage
on:
  pull_request:
    branches: [main]
jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""


class TestCq004Success:
    @pytest.mark.asyncio
    async def test_coverage_yml_returns_true(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "coverage.yml").write_text(_VALID_COVERAGE_YAML)
        ws = _FakeWorkspace(tmp_path)
        assert await cq004_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_coverage_yaml_extension(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "coverage.yaml").write_text(_VALID_COVERAGE_YAML)
        ws = _FakeWorkspace(tmp_path)
        assert await cq004_success(ws, _make_ctx()) is True

    @pytest.mark.asyncio
    async def test_malformed_yaml_returns_false(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "coverage.yml").write_text(_MALFORMED_YAML)
        ws = _FakeWorkspace(tmp_path)
        assert await cq004_success(ws, _make_ctx()) is False

    @pytest.mark.asyncio
    async def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        ws = _FakeWorkspace(tmp_path)
        assert await cq004_success(ws, _make_ctx()) is False


# ---------------------------------------------------------------------------
# repo001_success
# ---------------------------------------------------------------------------


class TestRepo001Success:
    @pytest.mark.asyncio
    async def test_protected_with_reviews_returns_true(self) -> None:
        bp = MagicMock()
        bp.is_protected = True
        bp.required_reviews = 1
        ctx = _make_ctx(branch_protection=bp)
        ws = _FakeWorkspace(Path("/tmp"))
        assert await repo001_success(ws, ctx) is True

    @pytest.mark.asyncio
    async def test_not_protected_returns_false(self) -> None:
        bp = MagicMock()
        bp.is_protected = False
        bp.required_reviews = 1
        ctx = _make_ctx(branch_protection=bp)
        ws = _FakeWorkspace(Path("/tmp"))
        assert await repo001_success(ws, ctx) is False

    @pytest.mark.asyncio
    async def test_protected_but_no_reviews_returns_false(self) -> None:
        bp = MagicMock()
        bp.is_protected = True
        bp.required_reviews = 0
        ctx = _make_ctx(branch_protection=bp)
        ws = _FakeWorkspace(Path("/tmp"))
        assert await repo001_success(ws, ctx) is False

    @pytest.mark.asyncio
    async def test_none_branch_protection_returns_false(self) -> None:
        ctx = _make_ctx(branch_protection=None)
        ws = _FakeWorkspace(Path("/tmp"))
        assert await repo001_success(ws, ctx) is False
