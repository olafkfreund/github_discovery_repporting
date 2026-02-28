from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.enums import ReportStatus

# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------


class ReportCreate(BaseModel):
    """Payload for generating a new report from a completed scan.

    ``scan_id`` is provided via the URL path, so it is not required in the
    request body.
    """

    title: str | None = None
    template_id: UUID | None = None


class ReportResponse(BaseModel):
    """Report record returned in list and summary responses.

    ``ai_summary`` and ``ai_recommendations`` are intentionally excluded here
    to keep list payloads small.  Use ``ReportDetailResponse`` when the full
    AI-generated content is needed.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scan_id: UUID
    customer_id: UUID
    title: str
    generated_at: datetime
    overall_score: float | None
    dora_level: str | None
    pdf_path: str | None
    status: ReportStatus
    created_at: datetime
    updated_at: datetime


class ReportDetailResponse(ReportResponse):
    """Full report record including AI-generated content."""

    ai_summary: str | None = None
    ai_recommendations: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# ReportTemplate schemas
# ---------------------------------------------------------------------------


class TemplateCreate(BaseModel):
    """Payload for creating a new report template."""

    name: str
    description: str | None = None
    is_default: bool = False
    header_logo_path: str | None = None
    accent_color: str = "#2563eb"
    include_sections: list[str] | None = None
    custom_css: str | None = None


class TemplateResponse(BaseModel):
    """Report template record returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_default: bool
    accent_color: str
    include_sections: list[str] | None
    created_at: datetime
