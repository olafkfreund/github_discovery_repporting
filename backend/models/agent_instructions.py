from __future__ import annotations

"""SQLAlchemy model for per-customer agent runtime instructions."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.customer import Customer


class AgentInstructions(UUIDMixin, TimestampMixin, Base):
    """Per-customer instructions injected into the remediation agent context.

    Used when the target repository does not contain an AGENTS.md, CLAUDE.md,
    ``.cursorrules``, or ``.github/copilot-instructions.md`` of its own.
    Exactly one row per customer is enforced by the unique constraint on
    ``customer_id``.  Per-connection overrides are stored on
    ``PlatformConnection.agent_instructions_override``.

    Attributes:
        customer_id: FK to the owning customer; cascades on delete.
        content: Markdown or plain-text body injected into agent context.
        enabled: When ``False`` the row is stored but not injected.  Allows
            toggling without deleting the content.
    """

    __tablename__ = "agent_instructions"
    __table_args__ = (UniqueConstraint("customer_id", name="uq_agent_instructions_customer_id"),)

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    customer: Mapped[Customer] = relationship(
        "Customer",
        back_populates="agent_instructions",
    )
