from __future__ import annotations

"""Pydantic schemas for the Skill system.

Covers the YAML-frontmatter contract for built-in skill markdown files and the
CRUD data-transfer objects used by the service layer and (eventually) the router.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SkillFrontmatter(BaseModel):
    """YAML frontmatter contract for a skill markdown file.

    Every ``.md`` file in ``backend/skills/library/`` must begin with a YAML
    block enclosed in ``---`` delimiters that satisfies this schema.

    Attributes:
        name: URL-safe slug; must match the file's stem exactly.
        description: One-sentence summary of what the skill teaches.
        category: Scanner category key or ``"general"`` for cross-cutting skills.
        applies_to: List of check IDs (e.g. ``REPO-001``) this skill addresses.
            An empty list means the skill applies to every check ("always-on").
        triggers: Contexts in which the skill body is injected. Defaults to both
            ``remediation`` and ``scan_enrichment`` if omitted.
        version: Schema version integer, starting at 1.
        authored_by: Attribution string; ``"builtin"`` for library files.
        tags: Optional free-form tags for future filtering.
    """

    name: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-z0-9-]+$")
    description: str = Field(..., min_length=1, max_length=512)
    category: str = Field(..., max_length=48)
    applies_to: list[str] = Field(default_factory=list)
    triggers: list[Literal["remediation", "scan_enrichment"]] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    authored_by: str = Field(default="builtin")
    tags: list[str] = Field(default_factory=list)

    @field_validator("triggers", mode="after")
    @classmethod
    def _default_triggers(cls, v: list[str]) -> list[str]:
        """Return both trigger types when the frontmatter omits ``triggers``."""
        return v or ["remediation", "scan_enrichment"]


# ---------------------------------------------------------------------------
# CRUD DTOs
# ---------------------------------------------------------------------------


class SkillBase(BaseModel):
    """Shared fields for Skill create and read schemas."""

    name: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-z0-9-]+$")
    description: str = Field(..., min_length=1, max_length=512)
    category: str = Field(..., max_length=48)
    applies_to_check_ids: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    body: str = Field(..., min_length=1, max_length=50_000)
    enabled: bool = True


class SkillCreate(SkillBase):
    """Payload for creating a new custom Skill row."""


class SkillUpdate(BaseModel):
    """Partial-update payload for an existing Skill row.

    All fields are optional; only supplied fields are written.
    """

    description: str | None = None
    category: str | None = None
    applies_to_check_ids: list[str] | None = None
    triggers: list[str] | None = None
    body: str | None = None
    enabled: bool | None = None


class SkillRead(SkillBase):
    """Full Skill representation returned from the API.

    Inherits all ``SkillBase`` fields and adds persistence metadata.
    """

    id: UUID
    customer_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillSummary(BaseModel):
    """Lightweight summary of a skill, merging built-in and custom sources.

    Returned by ``list_available_skills``; does not include the full body.
    """

    name: str
    description: str
    category: str
    applies_to_check_ids: list[str]
    triggers: list[str]
    source: Literal["builtin", "custom"]
    enabled: bool
    version: int
    updated_at: datetime | None = None
