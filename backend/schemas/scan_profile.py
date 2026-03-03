from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ScanProfileCreate(BaseModel):
    """Payload for creating a new scan profile."""

    name: str
    description: str | None = None
    is_default: bool = False
    config: dict[str, Any]


class ScanProfileUpdate(BaseModel):
    """Payload for updating an existing scan profile."""

    name: str | None = None
    description: str | None = None
    is_default: bool | None = None
    config: dict[str, Any] | None = None


class ScanProfileResponse(BaseModel):
    """Scan profile record returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    name: str
    description: str | None
    is_default: bool
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
