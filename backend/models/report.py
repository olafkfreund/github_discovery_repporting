from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin
from backend.models.enums import ReportStatus

if TYPE_CHECKING:
    from backend.models.customer import Customer
    from backend.models.scan import Scan


class ReportTemplate(UUIDMixin, Base):
    """Reusable styling and section configuration for generated reports."""

    __tablename__ = "report_templates"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    header_logo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    accent_color: Mapped[str] = mapped_column(
        String, default="#2563eb", nullable=False
    )
    include_sections: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    custom_css: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    reports: Mapped[list[Report]] = relationship(
        "Report",
        back_populates="template",
        lazy="selectin",
    )


class Report(UUIDMixin, TimestampMixin, Base):
    """A generated assessment report for a customer scan."""

    __tablename__ = "reports"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_recommendations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dora_level: Mapped[str | None] = mapped_column(String, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        default=ReportStatus.pending, nullable=False
    )

    # Relationships
    scan: Mapped[Scan] = relationship("Scan", lazy="selectin")
    customer: Mapped[Customer] = relationship("Customer", lazy="selectin")
    template: Mapped[ReportTemplate | None] = relationship(
        "ReportTemplate",
        back_populates="reports",
        lazy="selectin",
    )
