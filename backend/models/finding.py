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
    category: Mapped[Category] = mapped_column(nullable=False)
    check_id: Mapped[str] = mapped_column(String, nullable=False)
    check_name: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[Severity] = mapped_column(nullable=False)
    status: Mapped[CheckStatus] = mapped_column(nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

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
    category: Mapped[Category] = mapped_column(nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    scan: Mapped[Scan] = relationship(
        "Scan",
        back_populates="scores",
    )
