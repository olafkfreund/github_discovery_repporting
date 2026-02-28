from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin
from backend.models.enums import Category, CheckStatus, Severity

if TYPE_CHECKING:
    from backend.models.scan import Scan, ScanRepo


class Finding(UUIDMixin, TimestampMixin, Base):
    """An individual check result recorded during a scan."""

    __tablename__ = "findings"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scan_repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scan_repos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    category: Mapped[Category] = mapped_column()
    check_id: Mapped[str] = mapped_column(String)
    check_name: Mapped[str] = mapped_column(String)
    severity: Mapped[Severity] = mapped_column()
    status: Mapped[CheckStatus] = mapped_column()
    detail: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    score: Mapped[float] = mapped_column(Float, default=0.0)

    # Relationships
    scan: Mapped[Scan] = relationship(
        "Scan",
        back_populates="findings",
    )
    scan_repo: Mapped[ScanRepo | None] = relationship(
        "ScanRepo",
        back_populates="findings",
    )


class ScanScore(UUIDMixin, Base):
    """Aggregated score for a category within a scan."""

    __tablename__ = "scan_scores"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[Category] = mapped_column()
    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)
    finding_count: Mapped[int] = mapped_column(Integer)
    pass_count: Mapped[int] = mapped_column(Integer)
    fail_count: Mapped[int] = mapped_column(Integer)

    # Relationships
    scan: Mapped[Scan] = relationship(
        "Scan",
        back_populates="scores",
    )
