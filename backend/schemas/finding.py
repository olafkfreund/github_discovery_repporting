from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.enums import Category, CheckStatus, Severity

# ---------------------------------------------------------------------------
# Finding schemas
# ---------------------------------------------------------------------------


class FindingResponse(BaseModel):
    """Individual check result returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scan_id: UUID
    scan_repo_id: UUID
    category: Category
    check_id: str
    check_name: str
    severity: Severity
    status: CheckStatus
    detail: str | None
    evidence: dict[str, Any] | None
    weight: float
    score: float


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
