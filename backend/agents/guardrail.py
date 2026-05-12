"""Diff-scope guardrail (REQ-061).

Verifies that an agent's staged diff stays inside the recipe's allowed
file globs + the cited finding's evidence-declared affected paths.
Also enforces forbidden_paths as a hard reject regardless of allow-list.

Called from runner_backend BEFORE provider.create_pull_request().
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.agents.workspace import WorkspaceInfo
    from backend.models.finding import Finding
    from backend.remediation.recipe import RemediationRecipe

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuardrailViolation:
    """Returned when the staged diff escapes the recipe's allowed scope.

    Attributes:
        files_out_of_scope: Changed files that matched neither the allow-list
            globs nor the evidence paths.
        files_in_forbidden_paths: Changed files that matched at least one
            forbidden glob — always a hard reject.
        allowed_globs: The recipe's ``file_glob_hints`` used in the check.
        forbidden_globs: The recipe's ``forbidden_paths`` used in the check.
        cited_evidence_paths: ``affected_paths`` extracted from the finding's
            ``evidence`` dict (relative, stripped of leading ``/``).
    """

    files_out_of_scope: list[str] = field(default_factory=list)
    files_in_forbidden_paths: list[str] = field(default_factory=list)
    allowed_globs: list[str] = field(default_factory=list)
    forbidden_globs: list[str] = field(default_factory=list)
    cited_evidence_paths: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        """Human-readable summary of the violation cause.

        Returns:
            A string starting with the violation category followed by the
            first up-to-five offending paths in brackets.
        """
        if self.files_in_forbidden_paths:
            return f"forbidden_paths_matched: {self.files_in_forbidden_paths[:5]}"
        return f"diff_out_of_scope: {self.files_out_of_scope[:5]}"


async def check_diff_scope(
    *,
    workspace: WorkspaceInfo,
    recipe: RemediationRecipe,
    finding: Finding,
) -> GuardrailViolation | None:
    """Run ``git diff --name-only HEAD`` against the workspace and check each
    changed file against the recipe's scope.

    Returns ``None`` when every changed file is allowed.  Returns a populated
    :class:`GuardrailViolation` otherwise.

    **Allow-list** = ``recipe.file_glob_hints`` (fnmatch) UNION
    ``finding.evidence['affected_paths']`` (exact match, normalised to relative
    paths).

    **Forbidden-list** = ``recipe.forbidden_paths`` (fnmatch).  Forbidden hits
    ALWAYS fail, even when the file is also inside the allow-list.

    An empty allow-list (no hints and no evidence paths) causes the function to
    return a violation listing all changed files in ``files_out_of_scope`` — the
    agent should not have changed any files for a stub recipe with no scope
    hints.  The caller must not open a PR in this case.

    Args:
        workspace: The :class:`~backend.agents.workspace.WorkspaceInfo`
            representing the checked-out repository.
        recipe: The :class:`~backend.remediation.recipe.RemediationRecipe`
            describing which files the agent is permitted to touch.
        finding: The :class:`~backend.models.finding.Finding` whose
            ``evidence`` dict may contain an ``affected_paths`` key.

    Returns:
        ``None`` if all changes are within scope; a :class:`GuardrailViolation`
        describing the out-of-scope or forbidden files otherwise.
    """
    changed = await _git_diff_name_only(workspace.path)

    if not changed:
        # No file changes means nothing to block; the runner will decide whether
        # to open a PR at all (probably not, since there's nothing to commit).
        return None

    forbidden_globs = list(recipe.forbidden_paths or ())
    forbidden_hits = [f for f in changed if any(fnmatch(f, g) for g in forbidden_globs)]
    if forbidden_hits:
        return GuardrailViolation(
            files_in_forbidden_paths=forbidden_hits,
            forbidden_globs=forbidden_globs,
            cited_evidence_paths=_evidence_paths(finding),
        )

    allowed_globs = list(recipe.file_glob_hints or ())
    evidence_paths = _evidence_paths(finding)

    if not allowed_globs and not evidence_paths:
        # No scope to check against — the agent should not have changed any
        # files for this recipe.  Report all changed files as out-of-scope so
        # the PR is blocked.
        return GuardrailViolation(
            files_out_of_scope=list(changed),
            allowed_globs=[],
            cited_evidence_paths=[],
        )

    out_of_scope: list[str] = []
    for path in changed:
        matches_glob = any(fnmatch(path, g) for g in allowed_globs)
        matches_evidence = path in evidence_paths
        if not (matches_glob or matches_evidence):
            out_of_scope.append(path)

    if out_of_scope:
        return GuardrailViolation(
            files_out_of_scope=out_of_scope,
            allowed_globs=allowed_globs,
            cited_evidence_paths=evidence_paths,
        )
    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _evidence_paths(finding: Finding) -> list[str]:
    """Extract ``affected_paths`` from ``finding.evidence``.

    Gracefully handles ``None`` evidence, missing ``affected_paths`` key, and
    non-list values.  Entries that are not strings are silently dropped.

    Args:
        finding: The :class:`~backend.models.finding.Finding` to inspect.

    Returns:
        A list of relative path strings (leading ``/`` stripped).  Returns
        ``[]`` when evidence is absent or malformed.
    """
    if not finding.evidence:
        return []
    paths = finding.evidence.get("affected_paths")
    if not isinstance(paths, list):
        return []
    return [str(p).lstrip("/") for p in paths if isinstance(p, str)]


async def _git_diff_name_only(workspace_path: Path) -> list[str]:
    """Run ``git diff --name-only HEAD`` and return the changed-file list.

    Uses ``HEAD`` as the comparison base so that both staged and unstaged
    changes relative to the last commit are captured.

    On git failure the function logs a warning and returns ``[]`` — a
    transient git error must not crash the runner; the caller will see an
    empty diff and treat it as "no changes" (skipping PR creation).

    Args:
        workspace_path: Absolute path to the cloned repository directory.

    Returns:
        A list of relative file paths reported by ``git diff --name-only HEAD``.
        Returns ``[]`` on empty diff or subprocess failure.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "diff",
        "--name-only",
        "HEAD",
        cwd=str(workspace_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(
            "guardrail: git diff failed (exit=%d): %s",
            proc.returncode,
            stderr.decode("utf-8", errors="replace")[:200],
        )
        return []
    return [line for line in stdout.decode("utf-8", errors="replace").splitlines() if line]
