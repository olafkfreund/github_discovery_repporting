from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin
from backend.models.enums import Category, CheckStatus, Severity


class CustomRequirement(UUIDMixin, TimestampMixin, Base):
    """A customer-specific check applied during scans."""

    __tablename__ = "custom_requirements"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[Category] = mapped_column(nullable=False)
    check_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[Severity] = mapped_column(nullable=False)
    evaluation_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    results: Mapped[list[RequirementResult]] = relationship(
        "RequirementResult",
        back_populates="requirement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RequirementResult(UUIDMixin, Base):
    """Outcome of evaluating a custom requirement against a specific scan."""

    __tablename__ = "requirement_results"

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("custom_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[CheckStatus] = mapped_column(nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    requirement: Mapped[CustomRequirement] = relationship(
        "CustomRequirement",
        back_populates="results",
    )
