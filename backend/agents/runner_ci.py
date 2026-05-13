from __future__ import annotations

"""CI-mode runner: dispatch a workflow on the customer's CI platform.

The agent's lifecycle when runtime_mode='ci':
  1. agent_service.create_agent_run inserts an AgentRun in 'pending' state.
  2. trigger_ci_run() is scheduled (analogous to trigger_backend_run).
  3. This module picks the right dispatch API based on the connection's
     platform (github / gitlab / azure_devops) and POSTs a workflow trigger.
  4. The customer's CI runner pulls the bps-agent CLI image (Phase 5) and
     runs it with the AgentRun ID + callback URL + HMAC secret.
  5. The agent CLI POSTs step events back to /api/agent-runs/{id}/events
     (shipped in #47). Each event is HMAC-signed using AgentRun.callback_secret.
  6. When the agent finishes, it POSTs a final 'status_change' event.

This module owns step 3 only. The customer-side workflow is illustrated by
the three YAML templates shipped alongside.
"""

import asyncio
import base64
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.config import settings
from backend.models.agent_runs import AgentRun
from backend.models.enums import AgentRunStatus

logger = logging.getLogger(__name__)


class CIDispatchError(RuntimeError):
    """Raised when workflow dispatch fails (auth, transport, or unknown platform)."""


async def dispatch_workflow(
    connection: Any,
    agent_run: AgentRun,
    *,
    callback_base_url: str,
    remediation_policy: Any | None = None,
) -> dict[str, Any]:
    """Trigger a workflow run on the customer's CI platform.

    Args:
        connection: The PlatformConnection ORM instance (github / gitlab /
            azure_devops). Provides credentials + base_url + org/group identifier.
        agent_run: The AgentRun row in pending state. Provides id and
            callback_secret (hex-encoded).
        callback_base_url: Where the customer-side workflow POSTs events.
            Typically settings.PUBLIC_API_BASE_URL.
        remediation_policy: Optional RemediationPolicy row supplying
            ci_workflow_repo and ci_workflow_ref. When None the caller must
            ensure the connection itself carries enough context (test usage).

    Returns:
        A provider-specific dict with ``{platform, dispatch_id, dispatch_url}``
        so the AgentRun row can be annotated for audit.

    Raises:
        CIDispatchError: on any HTTP/auth failure, unknown platform, or
            missing ci_workflow_repo configuration.
    """
    from backend.services.secrets_service import secrets_service  # noqa: PLC0415

    # Resolve platform string (may be enum or plain string).
    platform_raw = connection.platform
    platform = platform_raw.value if hasattr(platform_raw, "value") else str(platform_raw)

    # Validate ci_workflow_repo is configured.
    ci_workflow_repo: str | None = None
    ci_workflow_ref: str = "main"
    if remediation_policy is not None:
        ci_workflow_repo = remediation_policy.ci_workflow_repo
        ci_workflow_ref = remediation_policy.ci_workflow_ref or "main"

    if not ci_workflow_repo:
        raise CIDispatchError(
            f"ci_workflow_repo is not configured on the RemediationPolicy for "
            f"AgentRun {agent_run.id}. Set ci_workflow_repo before using CI mode."
        )

    # Decrypt platform credentials.
    raw_creds = secrets_service.decrypt(connection.credentials_encrypted)
    try:
        creds_dict: dict = json.loads(raw_creds)
    except json.JSONDecodeError:
        creds_dict = {}
    token = creds_dict.get("token", "")

    # Convert callback_secret bytes to hex string for the workflow inputs.
    callback_secret_hex = agent_run.callback_secret.hex()

    if platform == "github":
        return await _dispatch_github(
            connection=connection,
            agent_run=agent_run,
            callback_base_url=callback_base_url,
            token=token,
            ci_workflow_repo=ci_workflow_repo,
            ci_workflow_ref=ci_workflow_ref,
            callback_secret_hex=callback_secret_hex,
        )
    if platform == "gitlab":
        return await _dispatch_gitlab(
            connection=connection,
            agent_run=agent_run,
            callback_base_url=callback_base_url,
            token=token,
            ci_workflow_repo=ci_workflow_repo,
            ci_workflow_ref=ci_workflow_ref,
            callback_secret_hex=callback_secret_hex,
        )
    if platform == "azure_devops":
        return await _dispatch_azure_devops(
            connection=connection,
            agent_run=agent_run,
            callback_base_url=callback_base_url,
            token=token,
            ci_workflow_repo=ci_workflow_repo,
            ci_workflow_ref=ci_workflow_ref,
            callback_secret_hex=callback_secret_hex,
        )

    raise CIDispatchError(
        f"Unknown platform '{platform}' — cannot dispatch CI workflow. "
        "Supported platforms: github, gitlab, azure_devops."
    )


async def _dispatch_github(
    *,
    connection: Any,
    agent_run: AgentRun,
    callback_base_url: str,
    token: str,
    ci_workflow_repo: str,
    ci_workflow_ref: str,
    callback_secret_hex: str,
) -> dict[str, Any]:
    """Dispatch a GitHub Actions workflow_dispatch event.

    Endpoint: POST /repos/{owner}/{repo}/actions/workflows/bps-agent.yml/dispatches

    Args:
        connection: PlatformConnection ORM instance (provides base_url).
        agent_run: AgentRun row (provides id, allowed/denied path globs via policy).
        callback_base_url: BPS public URL for event callbacks.
        token: Decrypted GitHub PAT.
        ci_workflow_repo: "owner/repo" string.
        ci_workflow_ref: Branch/ref to dispatch on.
        callback_secret_hex: Hex-encoded HMAC secret for callback signing.

    Returns:
        ``{platform, dispatch_id, dispatch_url}``

    Raises:
        CIDispatchError: on any non-2xx HTTP response.
    """
    base_url = connection.base_url or "https://api.github.com"
    base_url = base_url.rstrip("/")
    # If base_url points to github.com (web UI URL), map to API URL.
    if base_url in ("https://github.com", "http://github.com"):
        base_url = "https://api.github.com"

    dispatch_url = f"{base_url}/repos/{ci_workflow_repo}/actions/workflows/bps-agent.yml/dispatches"

    body: dict[str, Any] = {
        "ref": ci_workflow_ref,
        "inputs": {
            "agent_run_id": str(agent_run.id),
            "callback_url": callback_base_url,
            "callback_secret_hex": callback_secret_hex,
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            dispatch_url,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    if not response.is_success:
        raise CIDispatchError(
            f"GitHub workflow dispatch failed for run {agent_run.id} "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    # GitHub returns 204 No Content on success — there is no dispatch_id in the
    # response body; we record the workflow file path as the dispatch identifier.
    return {
        "platform": "github",
        "dispatch_id": f"{ci_workflow_repo}:bps-agent.yml@{ci_workflow_ref}",
        "dispatch_url": dispatch_url,
    }


async def _dispatch_gitlab(
    *,
    connection: Any,
    agent_run: AgentRun,
    callback_base_url: str,
    token: str,
    ci_workflow_repo: str,
    ci_workflow_ref: str,
    callback_secret_hex: str,
) -> dict[str, Any]:
    """Trigger a GitLab CI pipeline via the pipeline trigger API.

    Endpoint: POST /api/v4/projects/{project_id}/pipeline?ref={ref}

    Args:
        connection: PlatformConnection ORM instance (provides base_url).
        agent_run: AgentRun row.
        callback_base_url: BPS public URL for event callbacks.
        token: Decrypted GitLab PAT (PRIVATE-TOKEN header).
        ci_workflow_repo: Numeric project_id string.
        ci_workflow_ref: Branch/ref to trigger on.
        callback_secret_hex: Hex-encoded HMAC secret for callback signing.

    Returns:
        ``{platform, dispatch_id, dispatch_url}``

    Raises:
        CIDispatchError: on any non-2xx HTTP response.
    """
    base_url = connection.base_url or "https://gitlab.com"
    base_url = base_url.rstrip("/")

    dispatch_url = f"{base_url}/api/v4/projects/{ci_workflow_repo}/pipeline"

    body: dict[str, Any] = {
        "ref": ci_workflow_ref,
        "variables": [
            {"key": "AGENT_RUN_ID", "value": str(agent_run.id)},
            {"key": "CALLBACK_URL", "value": callback_base_url},
            {"key": "CALLBACK_SECRET_HEX", "value": callback_secret_hex},
        ],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            dispatch_url,
            json=body,
            headers={
                "PRIVATE-TOKEN": token,
                "Content-Type": "application/json",
            },
        )

    if not response.is_success:
        raise CIDispatchError(
            f"GitLab pipeline trigger failed for run {agent_run.id} "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    resp_data = response.json()
    pipeline_id = resp_data.get("id", "unknown")
    pipeline_web_url = resp_data.get("web_url", dispatch_url)

    return {
        "platform": "gitlab",
        "dispatch_id": str(pipeline_id),
        "dispatch_url": pipeline_web_url,
    }


async def _dispatch_azure_devops(
    *,
    connection: Any,
    agent_run: AgentRun,
    callback_base_url: str,
    token: str,
    ci_workflow_repo: str,
    ci_workflow_ref: str,
    callback_secret_hex: str,
) -> dict[str, Any]:
    """Trigger an Azure Pipelines run via the Pipelines REST API.

    Endpoint: POST {org_url}/{project}/_apis/pipelines/{pipeline_id}/runs?api-version=7.0

    The ``ci_workflow_repo`` field encodes ``project_name:pipeline_id`` for
    Azure DevOps (e.g. ``"MyProject:42"``).  When no colon is present the
    entire value is treated as the project name and pipeline_id defaults to 1.

    Args:
        connection: PlatformConnection ORM instance (provides org_or_group as
            the Azure DevOps organisation URL or name, and base_url).
        agent_run: AgentRun row.
        callback_base_url: BPS public URL for event callbacks.
        token: Decrypted Azure DevOps PAT (used in Basic auth as ``:token``).
        ci_workflow_repo: ``"project_name:pipeline_id"`` or ``"project_name"``.
        ci_workflow_ref: Branch/ref to run on (refs/heads/... format preferred).
        callback_secret_hex: Hex-encoded HMAC secret for callback signing.

    Returns:
        ``{platform, dispatch_id, dispatch_url}``

    Raises:
        CIDispatchError: on any non-2xx HTTP response.
    """
    org = connection.org_or_group
    base_url = connection.base_url

    # Build the organisation URL.
    if base_url:
        org_url = base_url.rstrip("/")
    else:
        org_url = f"https://dev.azure.com/{org}"

    # Parse project and pipeline_id from ci_workflow_repo.
    if ":" in ci_workflow_repo:
        project_name, pipeline_id_str = ci_workflow_repo.split(":", 1)
    else:
        project_name = ci_workflow_repo
        pipeline_id_str = "1"

    dispatch_url = (
        f"{org_url}/{project_name}/_apis/pipelines/{pipeline_id_str}/runs?api-version=7.0"
    )

    # Normalise ref to refs/heads/... format for Azure Pipelines.
    ref_name = ci_workflow_ref
    if not ref_name.startswith("refs/"):
        ref_name = f"refs/heads/{ref_name}"

    body: dict[str, Any] = {
        "resources": {
            "repositories": {
                "self": {"refName": ref_name},
            },
        },
        "variables": {
            "AGENT_RUN_ID": {"value": str(agent_run.id)},
            "CALLBACK_URL": {"value": callback_base_url},
            "CALLBACK_SECRET_HEX": {"value": callback_secret_hex},
        },
    }

    # Azure DevOps uses Basic auth with `:token` base64-encoded.
    basic_token = base64.b64encode(f":{token}".encode()).decode()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            dispatch_url,
            json=body,
            headers={
                "Authorization": f"Basic {basic_token}",
                "Content-Type": "application/json",
            },
        )

    if not response.is_success:
        raise CIDispatchError(
            f"Azure Pipelines run trigger failed for run {agent_run.id} "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    resp_data = response.json()
    run_id = resp_data.get("id", "unknown")
    run_url = resp_data.get("_links", {}).get("web", {}).get("href", dispatch_url)

    return {
        "platform": "azure_devops",
        "dispatch_id": str(run_id),
        "dispatch_url": run_url,
    }


async def trigger_ci_run(
    agent_run: AgentRun,
    db_factory: async_sessionmaker,
) -> asyncio.Task:
    """Schedule the CI-platform workflow dispatch as a background task.

    Mirrors trigger_backend_run from agent_service for symmetry. Returns the
    asyncio.Task so callers can chain. The task performs:
      - load AgentRun + Scan + Connection + RemediationPolicy
      - call dispatch_workflow(connection, agent_run) per platform
      - on success: update AgentRun.status -> 'running'
      - on failure: update AgentRun.status -> 'failed', record error.

    Args:
        agent_run: The AgentRun row in pending state to schedule.
        db_factory: Application-wide async session factory.

    Returns:
        The asyncio.Task wrapping the dispatch coroutine.
    """
    run_id = agent_run.id
    logger.info("trigger_ci_run: scheduling CI workflow dispatch for run %s.", run_id)
    return asyncio.create_task(_run_ci_dispatch(run_id=run_id, db_factory=db_factory))


async def _run_ci_dispatch(
    *,
    run_id: UUID,
    db_factory: async_sessionmaker,
) -> None:
    """Internal coroutine: load DB state, dispatch workflow, update run status."""
    from backend.models.customer import PlatformConnection  # noqa: PLC0415
    from backend.models.remediation_policy import RemediationPolicy  # noqa: PLC0415
    from backend.models.scan import Scan  # noqa: PLC0415

    async with db_factory() as db:
        # Load AgentRun.
        result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            logger.error("_run_ci_dispatch: AgentRun %s not found.", run_id)
            return

        # Load Scan to get connection_id and customer_id.
        scan_result = await db.execute(select(Scan).where(Scan.id == run.scan_id))
        scan = scan_result.scalar_one_or_none()
        if scan is None:
            logger.error("_run_ci_dispatch: Scan %s not found for run %s.", run.scan_id, run_id)
            await _mark_failed(db_factory, run_id, f"Scan {run.scan_id} not found.")
            return

        # Load PlatformConnection.
        conn_result = await db.execute(
            select(PlatformConnection).where(PlatformConnection.id == scan.connection_id)
        )
        connection = conn_result.scalar_one_or_none()
        if connection is None:
            logger.error(
                "_run_ci_dispatch: PlatformConnection %s not found for run %s.",
                scan.connection_id,
                run_id,
            )
            await _mark_failed(
                db_factory,
                run_id,
                f"PlatformConnection {scan.connection_id} not found.",
            )
            return

        # Load RemediationPolicy (may be None — caller handles missing ci_workflow_repo).
        policy_result = await db.execute(
            select(RemediationPolicy).where(RemediationPolicy.customer_id == scan.customer_id)
        )
        remediation_policy = policy_result.scalar_one_or_none()

    # Dispatch outside the DB session to avoid holding it open during HTTP I/O.
    try:
        dispatch_result = await dispatch_workflow(
            connection,
            run,
            callback_base_url=settings.PUBLIC_API_BASE_URL,
            remediation_policy=remediation_policy,
        )
    except CIDispatchError as exc:
        logger.error("_run_ci_dispatch: dispatch failed for run %s: %s", run_id, exc)
        await _mark_failed(db_factory, run_id, f"ci_dispatch_error: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("_run_ci_dispatch: unexpected error for run %s.", run_id)
        await _mark_failed(db_factory, run_id, f"{type(exc).__name__}: {exc}")
        return

    # Update run to 'running' and record dispatch metadata.
    async with db_factory() as db:
        result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is not None:
            run.status = AgentRunStatus.running
            run.started_at = datetime.now(tz=UTC)
            # Store dispatch metadata in the error field (repurposed as audit note)
            # until a dedicated dispatch_metadata column is added in Phase 5.
            run.error = None  # clear any prior error
            await db.commit()

    logger.info(
        "_run_ci_dispatch: run %s dispatched to %s — dispatch_id=%s.",
        run_id,
        dispatch_result.get("platform"),
        dispatch_result.get("dispatch_id"),
    )


async def _mark_failed(
    db_factory: async_sessionmaker,
    run_id: UUID,
    error_msg: str,
) -> None:
    """Set AgentRun.status=failed and record the error message.

    Args:
        db_factory: Application-wide async session factory.
        run_id: UUID of the AgentRun to update.
        error_msg: Human-readable error description to store.
    """
    async with db_factory() as db:
        result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is not None:
            run.status = AgentRunStatus.failed
            run.error = error_msg
            run.finished_at = datetime.now(tz=UTC)
            await db.commit()
