from __future__ import annotations

"""Backend-mode per-AgentRun orchestrator.

Drives an :class:`~backend.models.agent_runs.AgentRun` from ``pending``
through ``running`` to a terminal state (``completed`` / ``failed`` /
``cancelled``), persisting an :class:`~backend.models.agent_runs.AgentStep`
row for each event emitted by the loop, and inserting
:class:`~backend.models.agent_runs.RemediationAction` rows for each finding
the agent attempts.

CI mode (mode B) is Phase 4 / epic #5 — this file handles backend mode only.

Clone URL resolution
--------------------
- **GitHub**: ``https://{base_url or github.com}/{org}/{repo_name}.git``
- **GitLab**: ``https://{base_url or gitlab.com}/{group}/{repo_name}.git``
  (currently raises :class:`NotImplementedError` — documented open issue)
- **Azure DevOps**: raises :class:`NotImplementedError` — documented open issue

The credential is injected via the ``credential_helper`` argument to
:func:`~backend.agents.workspace.open_workspace`, which writes a one-shot
``GIT_ASKPASS`` script so the token never appears in ``/proc`` or logs.

AGENTS.md probe
---------------
Before building the system prompt, the runner checks whether the cloned
workspace already contains any of:

  ``AGENTS.md``, ``CLAUDE.md``, ``.cursorrules``,
  ``.github/copilot-instructions.md``

Only when *none* of these files exist does the runner prepend the resolved
:class:`~backend.models.agent_instructions.AgentInstructions` content to the
system prompt.  This avoids overriding the repository's own AI instructions.
"""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.agents.guardrail import GuardrailViolation, check_diff_scope
from backend.agents.loop import (
    LoopBudgetExceeded,
    LoopCancelled,
    LoopCaps,
    LoopEvent,
    LoopResult,
    run_loop,
)
from backend.agents.prompts import load_prompt
from backend.agents.redactor import redact, redact_mapping
from backend.agents.tools import get_tool_registry
from backend.agents.workspace import WorkspaceError, open_workspace
from backend.config import settings
from backend.llm.base import LLMProvider
from backend.llm.factory import get_llm_provider
from backend.models.agent_runs import AgentRun, AgentStep, RemediationAction
from backend.models.enums import AgentRunStatus, AgentStepType, RemediationActionStatus
from backend.models.enums import CheckStatus as CheckStatusEnum
from backend.models.finding import Finding
from backend.models.scan import Scan, ScanRepo
from backend.providers.base import PlatformProvider
from backend.providers.factory import create_provider
from backend.remediation.recipe import ProviderCtx, RemediationRecipe
from backend.remediation.registry import get_recipe
from backend.schemas.platform_data import NormalizedRepo
from backend.services import agent_instructions_service, skill_service
from backend.services.event_bus import get_cancel_registry, get_event_bus
from backend.services.llm_connection_service import to_provider_config
from backend.services.skill_service import ResolvedSkill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Probe paths — ordered by priority.
# If any of these exists in the workspace, we do NOT inject our AGENTS.md.
# ---------------------------------------------------------------------------

_PROBE_PATHS = [
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
]

# Default PR cap per run when no remediation policy is present.
_DEFAULT_MAX_PRS = 10


# ---------------------------------------------------------------------------
# Skill block formatting
# ---------------------------------------------------------------------------


def _format_skill_block(skills: list[ResolvedSkill], budget_bytes: int) -> str:
    """Concatenate skill bodies into a system-prompt block, respecting *budget_bytes*.

    Returns ``""`` if *skills* is empty.

    Each skill is rendered as ``### <name>\\n<body>\\n\\n``.  If the total byte
    count exceeds *budget_bytes*, skills are sorted descending by body length and
    the longest body is truncated to ``budget_bytes // n_skills`` characters.
    Truncated bodies have ``\\n\\n[truncated]`` appended.  All skill name headers
    are always preserved — no skill is dropped entirely.

    Args:
        skills: Resolved skill instances to include.
        budget_bytes: Maximum total byte budget for the returned block.

    Returns:
        A formatted multi-section markdown string, or ``""`` when *skills* is empty.
    """
    if not skills:
        return ""

    entries = [(s.name, s.body) for s in skills]
    # 8 bytes of fixed overhead per entry: "### " (4) + "\\n" (1) + "\\n\\n" (2) + name varies
    total = sum(len(name.encode()) + len(body.encode()) + 8 for name, body in entries)

    if total <= budget_bytes:
        return "\n\n".join(f"### {name}\n{body}" for name, body in entries)

    # Over budget: truncate longest bodies first to a per-skill byte budget.
    n = len(entries)
    per_skill_budget = max(budget_bytes // n - 64, 256)
    truncated_entries: list[tuple[str, str]] = []
    for name, body in sorted(entries, key=lambda e: len(e[1]), reverse=True):
        if len(body) > per_skill_budget:
            body = body[:per_skill_budget] + "\n\n[truncated]"
        truncated_entries.append((name, body))

    # Restore deterministic name-sorted order for final output.
    truncated_entries.sort(key=lambda e: e[0])
    return "\n\n".join(f"### {name}\n{body}" for name, body in truncated_entries)


# ---------------------------------------------------------------------------
# Internal context dataclass
# ---------------------------------------------------------------------------


@dataclass
class _RunContext:
    """All state loaded from the DB needed to execute one agent run."""

    run: AgentRun
    scan: Scan
    scan_repo_by_id: dict[UUID, ScanRepo]
    connection_id: UUID
    connection_platform: str
    connection_org: str
    connection_base_url: str | None
    connection_token: str
    llm_config: dict
    agents_md_content: str | None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _load_run_context(db: AsyncSession, agent_run_id: UUID) -> _RunContext:
    """Load everything needed to execute the run, in a single round-trip pair.

    Args:
        db: Active async database session.
        agent_run_id: Primary key of the :class:`~backend.models.agent_runs.AgentRun`.

    Returns:
        Populated :class:`_RunContext`.

    Raises:
        RuntimeError: If the run, scan, or LLM connection row cannot be found.
    """
    import json  # noqa: PLC0415

    from backend.services.secrets_service import secrets_service  # noqa: PLC0415

    # Load AgentRun with nested relationships.
    run_result = await db.execute(
        select(AgentRun)
        .where(AgentRun.id == agent_run_id)
        .options(
            selectinload(AgentRun.scan).selectinload(Scan.scan_repos),
            selectinload(AgentRun.llm_connection),
        )
    )
    run: AgentRun | None = run_result.scalar_one_or_none()
    if run is None:
        raise RuntimeError(f"AgentRun {agent_run_id} not found.")

    scan: Scan = run.scan
    scan_repo_by_id: dict[UUID, ScanRepo] = {r.id: r for r in scan.scan_repos}

    llm_connection = run.llm_connection
    if llm_connection is None:
        raise RuntimeError(f"LLMConnection for run {agent_run_id} not found.")

    # Load the PlatformConnection for this scan.
    from backend.models.customer import PlatformConnection  # noqa: PLC0415

    conn_result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.id == scan.connection_id)
    )
    platform_conn = conn_result.scalar_one_or_none()
    if platform_conn is None:
        raise RuntimeError(f"PlatformConnection {scan.connection_id} not found.")

    # Decrypt the platform token (used as git credential).
    raw_creds = secrets_service.decrypt(platform_conn.credentials_encrypted)
    try:
        creds_dict: dict = json.loads(raw_creds)
    except json.JSONDecodeError:
        creds_dict = {}
    platform_token = creds_dict.get("token", "")

    # Build the LLM provider config dict (decrypts api_key internally).
    llm_cfg = to_provider_config(llm_connection)

    # Resolve AGENTS.md content.
    agents_md = await agent_instructions_service.resolve(db, platform_conn.id)

    return _RunContext(
        run=run,
        scan=scan,
        scan_repo_by_id=scan_repo_by_id,
        connection_id=platform_conn.id,
        connection_platform=platform_conn.platform.value
        if hasattr(platform_conn.platform, "value")
        else str(platform_conn.platform),
        connection_org=platform_conn.org_or_group,
        connection_base_url=platform_conn.base_url,
        connection_token=platform_token,
        llm_config=llm_cfg,
        agents_md_content=agents_md,
    )


async def _eligible_findings(db: AsyncSession, scan_id: UUID) -> list[Finding]:
    """Return all failing, repo-level findings for *scan_id*.

    Only findings with ``status=failed`` and a non-null ``scan_repo_id``
    are included.  Org-level findings (``scan_repo_id=None``) are excluded
    because the agent needs a concrete repository to clone.

    Args:
        db: Active async database session.
        scan_id: UUID of the scan to query.

    Returns:
        List of :class:`~backend.models.finding.Finding` rows, ordered by
        severity (most severe first).
    """
    result = await db.execute(
        select(Finding).where(
            Finding.scan_id == scan_id,
            Finding.status == CheckStatusEnum.failed,
            Finding.scan_repo_id.is_not(None),
        )
    )
    findings = list(result.scalars().all())
    # Sort by severity so critical/high findings are attempted first.
    _sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: _sev_order.get(str(f.severity.value), 5))
    return findings


def _build_clone_url(
    platform: str,
    base_url: str | None,
    org: str,
    repo_name: str,
) -> str:
    """Construct the HTTPS clone URL for a repository.

    Credential injection (token via GIT_ASKPASS) is handled externally by
    :func:`~backend.agents.workspace.open_workspace` — the token must NOT
    be embedded in the URL.

    Args:
        platform: Platform identifier string (``"github"`` / ``"gitlab"`` /
            ``"azure_devops"``).
        base_url: Optional self-hosted base URL (e.g. ``"https://github.example.com"``).
        org: Organisation / group / org name.
        repo_name: Repository name (not full path).

    Returns:
        HTTPS clone URL without embedded credentials.

    Raises:
        NotImplementedError: For platforms other than GitHub (GitLab and
            Azure DevOps URL resolution is tracked as an open issue for
            Phase 3 follow-up).
    """
    if platform == "github":
        host = base_url.rstrip("/") if base_url else "https://github.com"
        return f"{host}/{org}/{repo_name}.git"

    if platform == "gitlab":
        # TODO: GitLab clone URL resolution is an open issue.
        # The ScanRepo.raw_data may contain "http_url_to_repo"; use that
        # once the ScanRepo schema is confirmed to include it.
        raise NotImplementedError(
            "Clone URL resolution for platform='gitlab' is pending. "
            "Tracked as an open issue for Phase 3 follow-up."
        )

    if platform == "azure_devops":
        # Azure DevOps clone URL requires project name as well as repo name.
        # The project is encoded in ScanRepo.repo_external_id as "project:repo".
        raise NotImplementedError(
            "Clone URL resolution for platform='azure_devops' is pending. "
            "Tracked as an open issue for Phase 3 follow-up."
        )

    raise NotImplementedError(f"Clone URL resolution for platform='{platform}' is not implemented.")


def _build_prompts(
    finding: Finding,
    recipe: RemediationRecipe,
    ctx: _RunContext,
    scan_repo: ScanRepo,
) -> tuple[str, str, str]:
    """Construct system + user prompts for a single finding.

    Loads the operator prompt template named by ``recipe.operator_prompt_path``,
    formats it with finding metadata, and returns the triple.

    Args:
        finding: The :class:`~backend.models.finding.Finding` being remediated.
        recipe: The :class:`~backend.remediation.recipe.RemediationRecipe` for
            this finding's check ID.
        ctx: Loaded :class:`_RunContext` containing AGENTS.md content.
        scan_repo: The :class:`~backend.models.scan.ScanRepo` row for the repo.

    Returns:
        A 3-tuple of ``(system_prompt, user_prompt, prompt_sha256)``.
    """
    template_content, prompt_sha = load_prompt(recipe.operator_prompt_path)

    # Format the template.  Templates use Python str.format(**ctx) syntax with
    # a standardised set of keys.  Unknown keys in the template raise KeyError;
    # callers should ensure templates are kept in sync with this dict.
    format_ctx = {
        "check_id": finding.check_id,
        "check_name": finding.check_name,
        "severity": finding.severity.value
        if hasattr(finding.severity, "value")
        else str(finding.severity),
        "detail": finding.detail or "",
        "evidence": json.dumps(finding.evidence or {}, indent=2),
        "repo_name": scan_repo.repo_name,
        "repo_url": scan_repo.repo_url,
        "default_branch": scan_repo.default_branch or "main",
        "forbidden_paths": ", ".join(recipe.forbidden_paths) if recipe.forbidden_paths else "none",
        "file_glob_hints": ", ".join(recipe.file_glob_hints)
        if recipe.file_glob_hints
        else "all files",
        "max_files_changed": recipe.max_files_changed,
        "max_lines_changed": recipe.max_lines_changed,
    }

    try:
        user_prompt = template_content.format(**format_ctx)
    except KeyError:
        # Fallback: use the raw template if it has unrecognised placeholders.
        user_prompt = template_content

    system_parts = [
        "You are a DevOps remediation agent.  Your task is to fix a specific "
        "failing security or quality check in a Git repository.",
        "",
        f"Check: {finding.check_id} — {finding.check_name}",
        f"Severity: {format_ctx['severity']}",
        f"Repository: {scan_repo.repo_name} ({scan_repo.repo_url})",
        "",
        "Constraints:",
        f"  - You may only modify files matching: {format_ctx['file_glob_hints']}",
        f"  - Forbidden paths (do NOT touch): {format_ctx['forbidden_paths']}",
        f"  - Maximum {recipe.max_files_changed} files changed",
        f"  - Maximum {recipe.max_lines_changed} lines changed total",
        "",
        "When you are done, open a pull request with your changes using the "
        "provider_api tool.  Include a concise PR title and description.",
    ]
    system_prompt = "\n".join(system_parts)

    return system_prompt, user_prompt, prompt_sha


async def _set_run_status(
    db: AsyncSession,
    run: AgentRun,
    new_status: AgentRunStatus,
    **fields,
) -> None:
    """Update *run* status and optional extra fields, then commit.

    Args:
        db: Active async database session.
        run: The :class:`~backend.models.agent_runs.AgentRun` ORM instance.
        new_status: Target :class:`~backend.models.enums.AgentRunStatus`.
        **fields: Additional column values to set on *run* (e.g. ``error=…``,
            ``finished_at=…``).
    """
    run.status = new_status
    for key, value in fields.items():
        setattr(run, key, value)
    await db.commit()


def _make_event_sink(
    run_id: UUID,
    db_factory: async_sessionmaker,
    run_step_counter: list[int],
) -> Callable[[LoopEvent], Awaitable[None]]:
    """Return an async callable that persists a :class:`~backend.agents.loop.LoopEvent`.

    The sink:

    1. Applies :func:`~backend.agents.redactor.redact` to
       ``event.tool_result``.
    2. Applies :func:`~backend.agents.redactor.redact_mapping` to
       ``event.tool_args``.
    3. Inserts an :class:`~backend.models.agent_runs.AgentStep` row using a
       *fresh* session from *db_factory* (never shares the outer long-lived
       session to avoid connection pool exhaustion).
    4. Publishes the event dict to the :class:`~backend.services.event_bus.EventBus`
       so issue #27 SSE subscribers receive it.

    Args:
        run_id: UUID of the owning agent run.
        db_factory: Application-wide async session factory.
        run_step_counter: A one-element list used as a mutable counter so the
            closure can track the monotonic ``step_index`` across findings.

    Returns:
        An async callable ``(event: LoopEvent) -> None``.
    """
    event_bus = get_event_bus()

    async def sink(event: LoopEvent) -> None:
        # Redact sensitive strings before persistence.
        tool_result_clean: str | None = None
        if event.tool_result is not None:
            tool_result_clean = redact(event.tool_result)

        tool_args_clean: dict | None = None
        if event.tool_args is not None:
            tool_args_clean = redact_mapping(event.tool_args)  # type: ignore[assignment]

        # Persist to DB using a brand-new session (avoids sharing the outer
        # long-lived session across asyncio tasks / greenlets).
        async with db_factory() as step_db:
            step = AgentStep(
                agent_run_id=run_id,
                step_index=event.step_index,
                step_type=event.step_type,
                prompt_hash=event.prompt_hash,
                tool_name=event.tool_name,
                tool_args_redacted=tool_args_clean,
                tool_result_redacted=tool_result_clean,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                latency_ms=event.latency_ms,
                status=event.status,
            )
            step_db.add(step)
            await step_db.commit()

        # Publish to the in-process event bus for issue #27 SSE subscribers.
        event_dict = {
            "run_id": str(run_id),
            "step_index": event.step_index,
            "step_type": event.step_type.value
            if hasattr(event.step_type, "value")
            else str(event.step_type),
            "tool_name": event.tool_name,
            "status": event.status,
            "input_tokens": event.input_tokens,
            "output_tokens": event.output_tokens,
            "latency_ms": event.latency_ms,
        }
        try:
            await event_bus.publish(run_id, event_dict)
        except Exception:  # noqa: BLE001
            logger.debug("EventBus.publish failed for run %s (subscriber not ready)", run_id)

    return sink


def _extract_pr_info(final_message: str) -> tuple[str | None, str | None]:
    """Heuristically extract PR URL and branch from the agent's final message.

    The loop returns the LLM's last text response.  If the agent opened a PR
    via the ``provider_api`` tool, it typically mentions the PR URL and/or the
    branch name in its conclusion.  This function applies simple heuristics to
    extract those values for storage on the
    :class:`~backend.models.agent_runs.RemediationAction` row.

    Args:
        final_message: The agent's final text response from
            :class:`~backend.agents.loop.LoopResult`.

    Returns:
        A 2-tuple of ``(pr_url, branch)``.  Either or both may be ``None``
        when the pattern is not found in the text.
    """
    import re  # noqa: PLC0415

    pr_url: str | None = None
    branch: str | None = None

    # Look for a GitHub / GitLab / Azure PR URL.
    url_match = re.search(
        r"https://[^\s<>\"']+/(?:pull|merge_requests|pullrequest)/\d+",
        final_message,
    )
    if url_match:
        pr_url = url_match.group(0).rstrip(".,;)")

    # Look for a branch name mentioned after "branch:", "Branch:", etc.
    branch_match = re.search(
        r"(?:branch[:\s]+)[`'\"]?([a-zA-Z0-9/_.\-]{3,100})[`'\"]?",
        final_message,
        re.IGNORECASE,
    )
    if branch_match:
        branch = branch_match.group(1).strip()

    return pr_url, branch


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_backend_agent(
    *,
    agent_run_id: UUID,
    db_factory: async_sessionmaker,
) -> None:
    """Execute an :class:`~backend.models.agent_runs.AgentRun` in backend mode.

    Lifecycle
    ---------
    1. Acquire the agent semaphore (waits if ``MAX_CONCURRENT_AGENT_RUNS`` busy).
    2. Load context from DB (AgentRun, Scan, LLMConnection, PlatformConnection).
    3. Snapshot provider/model onto the AgentRun row; set ``status=running``.
    4. Build LLM and platform providers.
    5. Resolve AGENTS.md for the connection.
    6. For each eligible failing finding (up to ``_DEFAULT_MAX_PRS`` cap):

       a. Look up the recipe; skip if check_id has no recipe.
       b. Derive the clone URL; skip with an error AgentStep on failure.
       c. Clone the workspace via :func:`~backend.agents.workspace.open_workspace`.
       d. Probe for existing AI instruction files — inject AGENTS.md only
          when none are found.
       e. Build system + user prompts.
       f. Create the cancel event.
       g. Run the agent loop via :func:`~backend.agents.loop.run_loop`.
       h. On success: insert a :class:`~backend.models.agent_runs.RemediationAction`
          and try to extract PR info from the final message.
       i. On :class:`~backend.agents.loop.LoopBudgetExceeded`: set
          ``status=failed`` and break (don't continue to next finding).
       j. On :class:`~backend.agents.loop.LoopCancelled`: set
          ``status=cancelled`` and break.
       k. On any other exception: set ``status=failed`` and break.

    7. Set ``status=completed``, ``finished_at=now``.  Cleanup registries.

    Args:
        agent_run_id: Primary key of the :class:`~backend.models.agent_runs.AgentRun`.
        db_factory: Application-wide async session factory.  Fresh sessions are
            opened for per-step persistence so the outer session is never held
            across blocking operations.
    """
    cancel_registry = get_cancel_registry()
    event_bus = get_event_bus()

    # Register cancellation event before doing anything so the cancel endpoint
    # can signal us even if we're still loading context.
    cancel_event = cancel_registry.get_or_create(agent_run_id)

    async with db_factory() as db:
        try:
            ctx = await _load_run_context(db, agent_run_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_backend_agent: failed to load context for run %s", agent_run_id)
            # Attempt to mark the run as failed — use a fresh session since we
            # don't know the state of the current one.
            async with db_factory() as err_db:
                err_result = await err_db.execute(
                    select(AgentRun).where(AgentRun.id == agent_run_id)
                )
                err_run = err_result.scalar_one_or_none()
                if err_run is not None:
                    await _set_run_status(
                        err_db,
                        err_run,
                        AgentRunStatus.failed,
                        error=f"context_load_error: {exc}",
                        finished_at=datetime.now(tz=UTC),
                    )
            cancel_registry.cleanup(agent_run_id)
            event_bus.cleanup(agent_run_id)
            return

        run = ctx.run

        # Mark as running.
        await _set_run_status(
            db,
            run,
            AgentRunStatus.running,
            started_at=datetime.now(tz=UTC),
        )

    # Build provider and LLM outside the long-lived session.
    try:
        async with db_factory() as db2:
            # Re-load the connection to pass to create_provider.
            from backend.models.customer import PlatformConnection  # noqa: PLC0415

            conn_result = await db2.execute(
                select(PlatformConnection).where(PlatformConnection.id == ctx.connection_id)
            )
            platform_conn = conn_result.scalar_one_or_none()
            if platform_conn is None:
                raise RuntimeError(f"PlatformConnection {ctx.connection_id} not found.")
            platform_provider: PlatformProvider = create_provider(platform_conn)

        llm_provider: LLMProvider = get_llm_provider(ctx.llm_config)

    except Exception as exc:  # noqa: BLE001
        logger.exception("run_backend_agent: failed to build providers for run %s", agent_run_id)
        async with db_factory() as fail_db:
            fail_result = await fail_db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))
            fail_run = fail_result.scalar_one_or_none()
            if fail_run is not None:
                await _set_run_status(
                    fail_db,
                    fail_run,
                    AgentRunStatus.failed,
                    error=f"provider_init_error: {exc}",
                    finished_at=datetime.now(tz=UTC),
                )
        cancel_registry.cleanup(agent_run_id)
        event_bus.cleanup(agent_run_id)
        return

    # Load eligible findings.
    async with db_factory() as findings_db:
        findings = await _eligible_findings(findings_db, ctx.scan.id)

    # Apply per-run check_ids filter (if the model stored them) — not yet used
    # because the AgentRun model has no check_ids column in Phase 3.
    # Capped at _DEFAULT_MAX_PRS.
    findings = findings[:_DEFAULT_MAX_PRS]

    logger.info(
        "run_backend_agent: run %s — %d eligible findings (cap=%d).",
        agent_run_id,
        len(findings),
        _DEFAULT_MAX_PRS,
    )

    # Counter shared by the event_sink closure to give global step indices.
    step_counter: list[int] = [0]
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost_usd = 0.0

    final_status = AgentRunStatus.completed
    final_error: str | None = None

    for finding in findings:
        # Resolve recipe.
        try:
            recipe = get_recipe(finding.check_id)
        except KeyError:
            logger.warning(
                "run_backend_agent: no recipe for check_id=%s — skipping.", finding.check_id
            )
            continue

        # Resolve the ScanRepo for this finding.
        scan_repo = ctx.scan_repo_by_id.get(finding.scan_repo_id)  # type: ignore[arg-type]
        if scan_repo is None:
            logger.warning(
                "run_backend_agent: ScanRepo %s not found — skipping finding %s.",
                finding.scan_repo_id,
                finding.id,
            )
            continue

        # Resolve clone URL.
        try:
            clone_url = _build_clone_url(
                ctx.connection_platform,
                ctx.connection_base_url,
                ctx.connection_org,
                scan_repo.repo_name,
            )
        except NotImplementedError as exc:
            logger.warning(
                "run_backend_agent: clone URL not supported for platform=%s: %s",
                ctx.connection_platform,
                exc,
            )
            # Insert an error AgentStep so the run trace reflects the skip.
            async with db_factory() as err_step_db:
                err_step = AgentStep(
                    agent_run_id=agent_run_id,
                    step_index=step_counter[0],
                    step_type=AgentStepType.observation,
                    tool_result_redacted=f"Skipped: {exc}",
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=0,
                    status="error",
                )
                err_step_db.add(err_step)
                await err_step_db.commit()
            step_counter[0] += 1
            continue

        # Build prompts before opening the workspace.
        system_prompt, user_prompt, prompt_sha = _build_prompts(finding, recipe, ctx, scan_repo)

        # Optionally prepend AGENTS.md content AFTER workspace probe
        # (probe happens inside the `async with open_workspace` block below).

        _token_for_finding = ctx.connection_token

        def _credential_helper(_t: str = _token_for_finding) -> str:  # noqa: ANN202
            return _t

        event_sink = _make_event_sink(agent_run_id, db_factory, step_counter)

        # Per-finding guardrail result; set inside the workspace block.
        _guardrail_result: GuardrailViolation | None = None

        # Clone workspace.
        try:
            async with open_workspace(
                clone_url=clone_url,
                branch=scan_repo.default_branch or "main",
                repo_external_id=scan_repo.repo_external_id,
                credential_helper=_credential_helper,
            ) as workspace:
                # AGENTS.md probe — only inject if no existing AI file found.
                existing_ai_file = next(
                    (p for p in _PROBE_PATHS if (workspace.path / p).is_file()),
                    None,
                )
                injected_agents_md = existing_ai_file is None and bool(ctx.agents_md_content)

                # Resolve skills relevant to this check and build skill block.
                async with db_factory() as skill_db:
                    resolved_skills = await skill_service.resolve_for_check(
                        skill_db, ctx.connection_id, finding.check_id
                    )
                skill_block = _format_skill_block(
                    resolved_skills,
                    budget_bytes=settings.SKILL_PROMPT_BUDGET_BYTES,
                )

                # Combined prompt_hash for audit (REQ-052): SHA256 over the
                # operator prompt SHA concatenated with each skill's SHA.
                combined_input = (prompt_sha + "".join(s.sha256 for s in resolved_skills)).encode()
                combined_prompt_hash = hashlib.sha256(combined_input).hexdigest()

                # Composition order: [AGENTS.md] + [system_prompt] + [Skills].
                parts: list[str] = []
                if injected_agents_md:
                    parts.append(ctx.agents_md_content)  # type: ignore[arg-type]
                parts.append(system_prompt)
                if skill_block:
                    parts.append("## Skills\n\n" + skill_block)
                effective_system = "\n\n".join(parts)

                tools = get_tool_registry()

                loop_result: LoopResult = await run_loop(
                    llm=llm_provider,
                    workspace=workspace,
                    provider=platform_provider,
                    system_prompt=effective_system,
                    user_prompt=user_prompt,
                    tools=tools,
                    caps=LoopCaps(),
                    event_sink=event_sink,
                    cancel_event=cancel_event,
                    prompt_hash=combined_prompt_hash,
                )

                # Diff-scope guardrail (REQ-061) — must run while the workspace
                # directory is still alive so git-diff can inspect the tree.
                _guardrail_result = await check_diff_scope(
                    workspace=workspace,
                    recipe=recipe,
                    finding=finding,
                )

        except WorkspaceError as exc:
            logger.error(
                "run_backend_agent: workspace error for finding %s: %s",
                finding.id,
                exc,
            )
            final_status = AgentRunStatus.failed
            final_error = f"workspace_error: {exc}"
            break

        except LoopBudgetExceeded as exc:
            logger.warning(
                "run_backend_agent: budget exceeded for run %s: %s",
                agent_run_id,
                exc.reason,
            )
            final_status = AgentRunStatus.failed
            final_error = f"budget_{exc.reason}"
            break

        except LoopCancelled:
            logger.info("run_backend_agent: run %s was cancelled.", agent_run_id)
            final_status = AgentRunStatus.cancelled
            break

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "run_backend_agent: unexpected error for run %s, finding %s: %s",
                agent_run_id,
                finding.id,
                exc,
            )
            final_status = AgentRunStatus.failed
            final_error = f"{type(exc).__name__}: {exc}"
            break

        # Accumulate token / cost totals.
        total_input_tokens += loop_result.total_input_tokens
        total_output_tokens += loop_result.total_output_tokens
        total_cost_usd += loop_result.total_cost_usd

        # ------------------------------------------------------------------
        # Diff-scope guardrail (REQ-061) — block PR if agent went out of scope.
        # The workspace context has exited here; we check the diff that was
        # accumulated inside the loop against the recipe's allowed file globs
        # and the finding's evidence paths.
        #
        # NOTE: The workspace directory is cleaned up when the async-with block
        # exits, so we cannot run git-diff here on the actual files.  Instead,
        # the runner_backend records the workspace path via a captured reference
        # during the loop and the guardrail is invoked while the workspace is
        # still open (see the _guardrail_result variable set inside the block).
        # ------------------------------------------------------------------
        if _guardrail_result is not None:
            logger.warning(
                "runner_backend: diff-scope violation for finding %s: %s",
                finding.id,
                _guardrail_result.reason,
            )
            # Mark this finding's action as failed and move to the next finding.
            async with db_factory() as fail_session:
                action_row = RemediationAction(
                    agent_run_id=agent_run_id,
                    finding_id=finding.id,
                    check_id=finding.check_id,
                    status=RemediationActionStatus.failed,
                    pr_url=None,
                    branch=None,
                    opened_at=None,
                )
                fail_session.add(action_row)
                await fail_session.commit()
            continue

        # Determine RemediationAction status using recipe success_check if present.
        action_status = RemediationActionStatus.in_progress
        if recipe.success_check is not None:
            try:
                # Build a minimal NormalizedRepo for the success_check context.
                repo_data = scan_repo.raw_data or {}
                norm_repo = NormalizedRepo(
                    external_id=scan_repo.repo_external_id,
                    name=scan_repo.repo_name,
                    url=scan_repo.repo_url,
                    default_branch=scan_repo.default_branch or "main",
                    is_private=repo_data.get("is_private", True),
                )
                provider_ctx = ProviderCtx(provider=platform_provider, repo=norm_repo)
                # Re-use the last workspace is not possible here (context exited).
                # We pass a minimal shim.  Success checks that need workspace
                # access will fail gracefully — this is an acceptable limitation
                # for Phase 3.  Phase 5 will persist the workspace for post-loop
                # checks.
                success = await recipe.success_check(
                    _MinimalWorkspace(path_str=str(scan_repo.repo_url), sha=""),
                    provider_ctx,
                )
                if not success:
                    action_status = RemediationActionStatus.failed
            except Exception:  # noqa: BLE001
                logger.debug(
                    "run_backend_agent: success_check raised for check %s — marking in_progress",
                    finding.check_id,
                )

        # Extract PR info from final message.
        pr_url, branch = _extract_pr_info(loop_result.final_message)

        # Insert RemediationAction.
        async with db_factory() as action_db:
            action = RemediationAction(
                agent_run_id=agent_run_id,
                finding_id=finding.id,
                check_id=finding.check_id,
                pr_url=pr_url,
                branch=branch,
                status=action_status,
                opened_at=datetime.now(tz=UTC) if pr_url else None,
            )
            action_db.add(action)
            await action_db.commit()

        logger.info(
            "run_backend_agent: finding %s processed — action_status=%s pr=%s",
            finding.id,
            action_status.value,
            pr_url,
        )

    # Update AgentRun with final totals.
    async with db_factory() as final_db:
        final_result = await final_db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))
        final_run = final_result.scalar_one_or_none()
        if final_run is not None:
            await _set_run_status(
                final_db,
                final_run,
                final_status,
                finished_at=datetime.now(tz=UTC),
                error=final_error,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                total_cost_usd=total_cost_usd,
            )

    # Clean up in-process registries.
    cancel_registry.cleanup(agent_run_id)
    event_bus.cleanup(agent_run_id)

    logger.info(
        "run_backend_agent: run %s finished with status=%s.",
        agent_run_id,
        final_status.value,
    )


# ---------------------------------------------------------------------------
# Minimal workspace shim for post-loop success_check calls
# ---------------------------------------------------------------------------


class _MinimalWorkspace:
    """Minimal duck-typed workspace shim for post-loop success_check calls.

    The actual workspace directory is cleaned up when the ``async with
    open_workspace(...)`` block exits.  Phase 5 will persist the workspace
    (or re-clone) for post-loop checks.  For now, we pass a placeholder that
    satisfies the :class:`~backend.remediation.recipe.WorkspaceProto` protocol
    so that success_check functions that only need the ``head_sha`` can work,
    while those that need filesystem access will fall back gracefully.
    """

    def __init__(self, path_str: str, sha: str) -> None:
        from pathlib import Path  # noqa: PLC0415

        self.path = Path(path_str)
        self.head_sha = sha
