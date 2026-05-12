"""Shared success-check callables used by first-class remediation recipes.

Each function verifies that a specific check's remediation is in place —
either by inspecting workspace files or by querying the provider API.

All callables are ``async`` and share the signature::

    async def <name>(workspace: WorkspaceProto, ctx: ProviderCtx) -> bool

where ``workspace`` is duck-typed to have ``.path`` (a :class:`pathlib.Path`)
and ``.head_sha`` (a ``str``), and ``ctx`` carries the provider + repo.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from backend.remediation.recipe import ProviderCtx, WorkspaceProto


async def repo001_success(workspace: WorkspaceProto, ctx: ProviderCtx) -> bool:
    """Verify branch protection is enabled with required PR reviews.

    Re-fetches the repo assessment data from the provider and checks that
    branch protection is enabled **and** pull-request reviews are required.

    Args:
        workspace: Checked-out workspace (not used for this provider-API check).
        ctx: Contains the authenticated provider and the target repo.

    Returns:
        ``True`` if ``branch_protection.is_protected`` and
        ``branch_protection.required_reviews >= 1`` are both true,
        ``False`` otherwise.
    """
    data = await ctx.provider.get_repo_assessment_data(ctx.repo)
    bp = data.branch_protection
    if bp is None:
        return False
    return bp.is_protected and bp.required_reviews >= 1


async def repo008_success(workspace: WorkspaceProto, ctx: ProviderCtx) -> bool:
    """Verify a CODEOWNERS file is present at one of the standard locations.

    Checks for the file at ``.github/CODEOWNERS``, ``CODEOWNERS`` (root),
    and ``docs/CODEOWNERS`` — in that order — returning ``True`` on the first
    match.

    Args:
        workspace: Checked-out workspace; uses ``workspace.path``.
        ctx: Not used for this file-based check.

    Returns:
        ``True`` if a CODEOWNERS file exists at any of the standard paths.
    """
    for rel in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        if (workspace.path / rel).is_file():
            return True
    return False


async def secrets003_success(workspace: WorkspaceProto, ctx: ProviderCtx) -> bool:
    """Verify a valid ``.gitleaks.toml`` file is present at the repo root.

    The file must exist **and** parse successfully as TOML — a malformed
    configuration file is treated as absent because gitleaks would reject it.

    Args:
        workspace: Checked-out workspace; uses ``workspace.path``.
        ctx: Not used for this file-based check.

    Returns:
        ``True`` if ``.gitleaks.toml`` exists and is valid TOML.
    """
    path = workspace.path / ".gitleaks.toml"
    if not path.is_file():
        return False
    try:
        tomllib.loads(path.read_text(encoding="utf-8"))
        return True
    except tomllib.TOMLDecodeError:
        return False


async def cicd001_success(workspace: WorkspaceProto, ctx: ProviderCtx) -> bool:
    """Verify a CodeQL workflow file is present and parses as valid YAML.

    Checks the four standard CodeQL workflow locations; the first file found
    is parsed as YAML.  A malformed YAML file is treated as not-yet-fixed
    because GitHub Actions would reject it.

    Args:
        workspace: Checked-out workspace; uses ``workspace.path``.
        ctx: Not used for this file-based check.

    Returns:
        ``True`` if a valid CodeQL workflow YAML exists at a standard path.
    """
    candidates = [
        ".github/workflows/codeql.yml",
        ".github/workflows/codeql.yaml",
        ".github/workflows/codeql-analysis.yml",
        ".github/workflows/codeql-analysis.yaml",
    ]
    for rel in candidates:
        path = workspace.path / rel
        if not path.is_file():
            continue
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
            return True
        except yaml.YAMLError:
            # Malformed YAML — report as not-yet-fixed.
            return False
    return False


async def cq004_success(workspace: WorkspaceProto, ctx: ProviderCtx) -> bool:
    """Verify a coverage workflow file is present and parses as valid YAML.

    Checks for ``coverage.yml`` and ``coverage.yaml`` under ``.github/workflows/``.
    A malformed YAML file is treated as not-yet-fixed.

    Args:
        workspace: Checked-out workspace; uses ``workspace.path``.
        ctx: Not used for this file-based check.

    Returns:
        ``True`` if a valid coverage workflow YAML exists at a standard path.
    """
    for rel in (".github/workflows/coverage.yml", ".github/workflows/coverage.yaml"):
        path = workspace.path / rel
        if not path.is_file():
            continue
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
            return True
        except yaml.YAMLError:
            return False
    return False
