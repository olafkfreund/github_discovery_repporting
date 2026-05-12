from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import Category, CheckStatus, Severity

# ---------------------------------------------------------------------------
# Finding enrichment schema
# ---------------------------------------------------------------------------


class FindingEnrichment(BaseModel):
    """Structured output of the post-scan enrichment LLM call.

    Persisted to Finding.ai_enrichment as a dict (model_dump).
    """

    explanation: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Plain-English why-this-matters tied to the finding's evidence.",
    )
    suggested_remediation_summary: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Short description of the recommended fix.",
    )
    confidence: Literal["low", "medium", "high"]
    skill_versions: dict[str, int] = Field(
        default_factory=dict,
        description="Map of skill_name -> version that contributed to this enrichment.",
    )


# ---------------------------------------------------------------------------
# Finding schemas
# ---------------------------------------------------------------------------


class FindingResponse(BaseModel):
    """Individual check result returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scan_id: UUID
    scan_repo_id: UUID | None
    category: Category
    check_id: str
    check_name: str
    severity: Severity
    status: CheckStatus
    detail: str | None
    evidence: dict[str, Any] | None
    weight: float
    score: float
    ai_enrichment: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Finding query-parameter filter schema
# ---------------------------------------------------------------------------


class FindingFilter(BaseModel):
    """Query-parameter filter applied when listing findings.

    All fields are optional; omitting a field means no filtering on that
    dimension.  Values are intentionally typed as ``str | None`` rather than
    the corresponding enum types so that invalid query strings produce a clear
    422 validation error from the router layer rather than a silent match
    failure.
    """

    category: str | None = None
    severity: str | None = None
    status: str | None = None
