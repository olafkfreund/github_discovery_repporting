from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.models.enums import AuthType, Platform

# ---------------------------------------------------------------------------
# Customer schemas
# ---------------------------------------------------------------------------


class CustomerCreate(BaseModel):
    """Payload for creating a new customer record."""

    name: str
    contact_email: str | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    """Partial payload for updating an existing customer record."""

    name: str | None = None
    contact_email: str | None = None
    notes: str | None = None


class CustomerResponse(BaseModel):
    """Full customer record returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    contact_email: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PlatformConnection schemas
# ---------------------------------------------------------------------------


class ConnectionCreate(BaseModel):
    """Payload for registering a new platform connection for a customer.

    ``credentials`` is accepted as plaintext and will be encrypted before
    persistence.  It is never returned in any response schema.
    """

    platform: Platform
    display_name: str
    base_url: str | None = None
    auth_type: AuthType
    credentials: str
    org_or_group: str


class ConnectionUpdate(BaseModel):
    """Partial payload for updating an existing platform connection."""

    display_name: str | None = None
    base_url: str | None = None
    auth_type: str | None = None
    credentials: str | None = None
    org_or_group: str | None = None
    is_active: bool | None = None


class ConnectionResponse(BaseModel):
    """Platform connection record returned from the API.

    ``credentials`` / ``credentials_encrypted`` are intentionally excluded
    from this schema to prevent credential leakage.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    platform: Platform
    display_name: str
    base_url: str | None
    auth_type: AuthType
    org_or_group: str
    is_active: bool
    last_validated_at: datetime | None
    created_at: datetime
    updated_at: datetime
