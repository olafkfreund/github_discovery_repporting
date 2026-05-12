from __future__ import annotations

"""Pydantic schemas for per-customer agent instructions CRUD endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentProfile(BaseModel):
    """Public-facing profile metadata for the picker UI."""

    slug: str
    display_name: str
    short_description: str


class AgentProfileContent(BaseModel):
    """Full profile body."""

    slug: str
    body: str


class AgentProfilesResponse(BaseModel):
    """Response envelope for the profile list endpoint."""

    profiles: list[AgentProfile]


class AgentInstructionsBase(BaseModel):
    """Shared fields for create and update payloads."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description=(
            "Markdown body injected into the remediation agent context when "
            "the target repository has no AGENTS.md / CLAUDE.md of its own. "
            "Plain text and Markdown are both accepted."
        ),
    )
    enabled: bool = Field(
        True,
        description=(
            "When False the row is stored but not injected. "
            "Use this to temporarily disable instructions without losing content."
        ),
    )
    profile_slug: str | None = Field(
        None,
        max_length=64,
        description=(
            "Slug of the built-in AGENTS.md profile selected for this customer "
            "(e.g. 'standard', 'banking', 'public-sector', 'strict'). "
            "Null when no profile has been selected or when the customer uses "
            "fully custom instructions."
        ),
    )


class AgentInstructionsUpsertPayload(AgentInstructionsBase):
    """PUT body — atomically replaces both ``content`` and ``enabled``."""

    pass


class AgentInstructionsRead(AgentInstructionsBase):
    """Agent instructions record returned by the API."""

    id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
