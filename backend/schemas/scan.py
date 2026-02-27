from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.enums import Category, ScanStatus

# ---------------------------------------------------------------------------
# Scan schemas
# ---------------------------------------------------------------------------


class ScanCreate(BaseModel):
    """Payload for triggering a new scan against a platform connection."""

    connection_id: UUID
    scan_config: dict[str, Any] | None = None


class ScanResponse(BaseModel):
    """Scan record returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    connection_id: UUID
    status: ScanStatus
    started_at: datetime | None
    completed_at: datetime | None
    total_repos: int
    error_message: str | None
    scan_config: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ScanRepo schemas
# ---------------------------------------------------------------------------


class ScanRepoResponse(BaseModel):
    """Repository record discovered and evaluated during a scan."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scan_id: UUID
    repo_name: str
    repo_url: str
    default_branch: str | None


# ---------------------------------------------------------------------------
# ScanScore schemas
# ---------------------------------------------------------------------------


class ScanScoreResponse(BaseModel):
    """Aggregated category score for a completed scan."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scan_id: UUID
    category: Category
    score: float
    max_score: float
    weight: float
    finding_count: int
    pass_count: int
    fail_count: int
