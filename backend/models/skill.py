from __future__ import annotations

"""SQLAlchemy models for the Skill system.

``Skill`` stores customer-authored (custom) skill rows; built-in skills live as
markdown files under ``backend/skills/library/`` and never become DB rows.
``SkillToggle`` allows per-customer on/off overrides for both built-in and
custom skills by name.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.customer import Customer


class Skill(UUIDMixin, TimestampMixin, Base):
    """Customer-authored skill.

    Built-in skills live as ``.md`` files and are never stored in this table.
    Exactly one custom skill per customer is allowed per name, enforced by the
    unique constraint on ``(customer_id, name)``.

    Attributes:
        customer_id: FK to the owning customer; cascades on delete.
        name: URL-safe slug, unique per customer.
        description: One-sentence summary.
        category: Scanner category key or ``"general"``.
        applies_to_check_ids: JSON list of check IDs this skill addresses.
            An empty list means the skill applies to every check ("always-on").
        triggers: JSON list of trigger contexts (``remediation``,
            ``scan_enrichment``).
        body: Full markdown body injected into the agent context.
        version: Integer incremented on every update.
        enabled: When ``False`` the skill is stored but never injected.
    """

    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("customer_id", "name", name="uq_skills_customer_name"),)

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    applies_to_check_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    triggers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    customer: Mapped[Customer] = relationship("Customer", back_populates="skills")


class SkillToggle(UUIDMixin, TimestampMixin, Base):
    """Per-customer enabled/disabled override for a skill (built-in or custom).

    Identifies the skill by ``skill_name`` (the slug) rather than a FK, so it
    can address both built-in markdown skills and DB-backed custom skills
    without a hard dependency.

    The unique constraint ensures at most one override row per
    ``(customer_id, skill_name)`` pair.

    Attributes:
        customer_id: FK to the owning customer; cascades on delete.
        skill_name: Slug of the skill being overridden.
        enabled: Desired enabled state for this customer.
    """

    __tablename__ = "skill_toggles"
    __table_args__ = (UniqueConstraint("customer_id", "skill_name", name="uq_skill_toggles"),)

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    customer: Mapped[Customer] = relationship("Customer", back_populates="skill_toggles")
