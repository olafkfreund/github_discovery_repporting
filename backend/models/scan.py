from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin
from backend.models.enums import ScanStatus

if TYPE_CHECKING:
    from backend.models.customer import Customer, PlatformConnection
    from backend.models.finding import Finding, ScanScore


class Scan(UUIDMixin, TimestampMixin, Base):
    """A single assessment run against a customer's platform connection."""

    __tablename__ = "scans"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ScanStatus] = mapped_column(default=ScanStatus.pending)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_repos: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    scan_config: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Relationships
    customer: Mapped[Customer] = relationship(
        "Customer",
        back_populates="scans",
    )
    connection: Mapped[PlatformConnection] = relationship(
        "PlatformConnection",
        back_populates="scans",
    )
    scan_repos: Mapped[list[ScanRepo]] = relationship(
        "ScanRepo",
        back_populates="scan",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    findings: Mapped[list[Finding]] = relationship(
        "Finding",
        back_populates="scan",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    scores: Mapped[list[ScanScore]] = relationship(
        "ScanScore",
        back_populates="scan",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ScanRepo(UUIDMixin, TimestampMixin, Base):
    """A repository discovered and evaluated during a scan."""

    __tablename__ = "scan_repos"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repo_external_id: Mapped[str] = mapped_column(String)
    repo_name: Mapped[str] = mapped_column(String)
    repo_url: Mapped[str] = mapped_column(String)
    default_branch: Mapped[str | None] = mapped_column(String)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Relationships
    scan: Mapped[Scan] = relationship(
        "Scan",
        back_populates="scan_repos",
    )
    findings: Mapped[list[Finding]] = relationship(
        "Finding",
        back_populates="scan_repo",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
