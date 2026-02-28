from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin
from backend.models.enums import AuthType, Platform

if TYPE_CHECKING:
    from backend.models.scan import Scan


class Customer(UUIDMixin, TimestampMixin, Base):
    """Represents a customer organisation being assessed."""

    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    contact_email: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    platform_connections: Mapped[list[PlatformConnection]] = relationship(
        "PlatformConnection",
        back_populates="customer",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    scans: Mapped[list[Scan]] = relationship(
        "Scan",
        back_populates="customer",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PlatformConnection(UUIDMixin, TimestampMixin, Base):
    """Stores credentials and metadata for a customer's DevOps platform."""

    __tablename__ = "platform_connections"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[Platform] = mapped_column()
    display_name: Mapped[str] = mapped_column(String)
    base_url: Mapped[str | None] = mapped_column(String)
    auth_type: Mapped[AuthType] = mapped_column()
    credentials_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    org_or_group: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Relationships
    customer: Mapped[Customer] = relationship(
        "Customer",
        back_populates="platform_connections",
    )
    scans: Mapped[list[Scan]] = relationship(
        "Scan",
        back_populates="connection",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
