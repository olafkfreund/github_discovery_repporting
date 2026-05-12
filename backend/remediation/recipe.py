"""RemediationRecipe dataclass and supporting types.

Defines the data contract for per-check remediation recipes used by the
agent remediator.  Each recipe describes *how* the agent should approach a
specific check finding — which strategy to use, which files it may touch,
and how to verify success.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from backend.providers.base import PlatformProvider
    from backend.schemas.platform_data import NormalizedRepo

from backend.scanners.base import Severity


class WorkspaceProto(Protocol):
    """Duck-typed shape needed by success_check functions.

    Both :class:`~backend.agents.workspace.WorkspaceInfo` and
    :class:`~backend.agents.tools.base.WorkspaceContext` satisfy this
    protocol — callers pass whichever is in scope.
    """

    @property
    def path(self):  # noqa: ANN201
        """Absolute path to the checked-out workspace directory."""
        ...  # pathlib.Path

    @property
    def head_sha(self) -> str:
        """Full 40-char SHA of HEAD at clone time."""
        ...


@dataclass
class ProviderCtx:
    """Context handed to a recipe's ``success_check`` callable.

    Attributes:
        provider: An authenticated :class:`~backend.providers.base.PlatformProvider`
            instance for the target platform.
        repo: The :class:`~backend.schemas.platform_data.NormalizedRepo` that
            the agent is remediating.
    """

    provider: PlatformProvider
    repo: NormalizedRepo


@dataclass(frozen=True)
class RemediationRecipe:
    """How the agent remediates one specific check finding.

    Attributes:
        check_id: The check identifier this recipe handles (e.g. ``"REPO-001"``).
        severity: Severity level of the check, used for prioritisation.
        default_strategy: Either ``"deterministic_template"`` (the agent follows
            a fixed template with no LLM improvisation) or ``"llm_freeform"``
            (the agent has latitude to analyse the repo and craft a fix).
        file_glob_hints: Glob patterns for files the agent is *allowed* to
            inspect or modify.  An empty list means the strategy is platform-API
            only (``requires_provider_api=True``) or all files are permitted.
        forbidden_paths: Paths the agent MUST NOT touch even if they match a
            glob hint.
        max_files_changed: Maximum number of files the agent may modify in a
            single remediation.  ``0`` means no file edits are permitted
            (provider-API-only recipes).
        max_lines_changed: Maximum total line delta across all changed files.
        operator_prompt_path: Filename (relative to the ``per_check/`` prompt
            directory) of the operator-level prompt template.
        requires_provider_api: When ``True`` the agent must call the provider's
            write API (e.g. :meth:`~backend.providers.base.PlatformProvider.set_branch_protection`)
            rather than editing files.
        success_check: Optional async callable that verifies the fix is in place.
            Signature: ``(workspace: WorkspaceProto, ctx: ProviderCtx) -> bool``.
            ``None`` for stub recipes — the agent uses heuristics or LLM judgement.
    """

    check_id: str
    severity: Severity
    default_strategy: Literal["deterministic_template", "llm_freeform"] = "llm_freeform"
    file_glob_hints: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    max_files_changed: int = 5
    max_lines_changed: int = 200
    operator_prompt_path: str = "generic.md"
    requires_provider_api: bool = False
    success_check: Callable[[WorkspaceProto, ProviderCtx], Awaitable[bool]] | None = None
