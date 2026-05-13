from __future__ import annotations

"""Pydantic schemas for the per-customer remediation policy CRUD endpoints."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RemediationPolicyBase(BaseModel):
    """Shared fields for the remediation policy upsert and read schemas."""

    enabled: bool = Field(
        default=False,
        description=(
            "Master toggle. When False the remediation agent will not act on any "
            "findings regardless of other settings."
        ),
    )
    auto_dispatch: bool = Field(
        default=False,
        description=(
            "When True a remediation AgentRun is automatically created and triggered "
            "after each completed scan."
        ),
    )
    kill_switch_enabled: bool = Field(
        default=False,
        description=(
            "Emergency stop. Overrides auto_dispatch; when True no agent runs will be "
            "dispatched even if auto_dispatch is True."
        ),
    )
    allowed_check_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit allowlist of check IDs the agent may act on. "
            "An empty list means all checks are allowed (subject to blocked_check_ids)."
        ),
    )
    blocked_check_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit denylist of check IDs the agent must never touch. "
            "Takes precedence over allowed_check_ids."
        ),
    )
    max_prs_per_scan: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Upper bound on the number of pull requests the agent may open per scan run.",
    )
    max_cost_usd_per_month: float = Field(
        default=100.0,
        ge=0.0,
        description=(
            "Soft monthly LLM-cost cap in USD. The agent runner checks this before each invocation."
        ),
    )
    allowed_path_globs: list[str] = Field(
        default_factory=list,
        description=(
            "Glob patterns restricting which paths the agent may modify "
            "(e.g. ['src/**', 'tests/**']). An empty list means all paths are allowed."
        ),
    )
    denied_path_globs: list[str] = Field(
        default_factory=list,
        description=(
            "Glob patterns explicitly excluded from agent modifications. "
            "Takes precedence over allowed_path_globs."
        ),
    )
    runtime_mode: Literal["backend", "ci"] = Field(
        default="backend",
        description="Where the agent runs — 'backend' (in-process) or 'ci' (via CI pipeline).",
    )
    oversight_mode: Literal["strict", "standard"] = Field(
        default="strict",
        description=(
            "Human-in-the-loop mode — 'strict' (PR review required before merge) or "
            "'standard' (agent may auto-merge low-risk fixes)."
        ),
    )
    llm_input_scope: Literal["hunk", "file", "repo-context"] = Field(
        default="hunk",
        description=(
            "How much code context is passed to the LLM per call — "
            "'hunk' (diff hunk only), 'file' (whole file), or 'repo-context' "
            "(repo-level context window)."
        ),
    )
    ci_workflow_repo: str | None = Field(
        default=None,
        description=(
            "CI workflow repo identifier. For GitHub: 'owner/repo'. "
            "For GitLab: 'project_id' (numeric string). "
            "For Azure DevOps: 'project_name'. "
            "When null, CI mode is unconfigured and trigger_ci_run will fail fast."
        ),
    )
    ci_workflow_ref: str = Field(
        default="main",
        description="Branch/ref to dispatch the CI workflow on (default 'main').",
    )


class RemediationPolicyUpsert(RemediationPolicyBase):
    """PUT body — replaces all policy fields atomically."""

    pass


class RemediationPolicyRead(RemediationPolicyBase):
    """Remediation policy record returned by the API."""

    id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
