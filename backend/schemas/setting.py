from __future__ import annotations

"""Pydantic schemas for the global settings singleton endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SettingBase(BaseModel):
    """Shared fields for the settings read and update schemas."""

    global_kill_switch_enabled: bool = Field(
        default=False,
        description=(
            "When True all agent runs are blocked across every customer, "
            "regardless of per-customer policy."
        ),
    )
    default_data_residency_region: str = Field(
        default="eu-west",
        max_length=32,
        description="ISO region tag for the default data residency zone (e.g. 'eu-west').",
    )
    audit_log_retention_days: int = Field(
        default=180,
        ge=30,
        le=3650,
        description="How many days audit log entries are retained before scheduled pruning.",
    )
    streaming_log_retention_hours: int = Field(
        default=72,
        ge=1,
        le=720,
        description="How many hours streaming run logs are retained before pruning.",
    )
    default_llm_connection_id: UUID | None = Field(
        default=None,
        description=(
            "Optional UUID of the global fallback LLM connection used when a customer "
            "has not configured one."
        ),
    )


class SettingRead(SettingBase):
    """Global settings record returned by the API."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SettingUpdate(BaseModel):
    """PUT body — partial update; only non-None sent fields are applied."""

    global_kill_switch_enabled: bool | None = Field(
        default=None,
        description="When True all agent runs are blocked globally.",
    )
    default_data_residency_region: str | None = Field(
        default=None,
        max_length=32,
        description="ISO region tag for the default data residency zone.",
    )
    audit_log_retention_days: int | None = Field(
        default=None,
        ge=30,
        le=3650,
        description="How many days audit log entries are retained.",
    )
    streaming_log_retention_hours: int | None = Field(
        default=None,
        ge=1,
        le=720,
        description="How many hours streaming run logs are retained.",
    )
    default_llm_connection_id: UUID | None = Field(
        default=None,
        description="Optional UUID of the global fallback LLM connection.",
    )
