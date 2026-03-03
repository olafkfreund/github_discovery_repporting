from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.customer import Customer


class ScanProfile(UUIDMixin, TimestampMixin, Base):
    """A reusable scan configuration profile belonging to a customer.

    Stores which categories/checks are enabled, custom weights, and
    threshold overrides.  The ``config`` JSON is snapshotted into
    ``Scan.scan_config`` at scan-trigger time so that results are
    reproducible even if the profile is later changed.
    """

    __tablename__ = "scan_profiles"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Relationships
    customer: Mapped[Customer] = relationship(
        "Customer",
        back_populates="scan_profiles",
    )
