from __future__ import annotations

"""Pydantic schemas for agent run, step, and remediation action endpoints."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.enums import AgentRunStatus, AgentStepType, RemediationActionStatus


class AgentStepRead(BaseModel):
    """Read shape for a single agent step."""

    id: UUID
    agent_run_id: UUID
    step_index: int
    step_type: AgentStepType
    prompt_hash: str | None
    tool_name: str | None
    tool_args_redacted: dict[str, Any] | None
    tool_result_redacted: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RemediationActionRead(BaseModel):
    """Read shape for a single remediation action."""

    id: UUID
    agent_run_id: UUID
    finding_id: UUID
    check_id: str
    pr_url: str | None
    branch: str | None
    status: RemediationActionStatus
    opened_at: datetime | None
    merged_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AgentRunListItem(BaseModel):
    """Compact shape for list views — no steps or actions."""

    id: UUID
    scan_id: UUID
    llm_connection_id: UUID
    provider: str
    model: str
    status: AgentRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    runtime_mode: str
    pr_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentRunRead(AgentRunListItem):
    """Full read shape including steps and actions."""

    error: str | None = None
    steps: list[AgentStepRead] = []
    actions: list[RemediationActionRead] = []


class AgentRunTriggerPayload(BaseModel):
    """Payload for triggering a new remediation agent run."""

    llm_connection_id: UUID
    runtime_mode: Literal["backend", "ci"] = "backend"
    check_ids: list[str] | None = None
