from __future__ import annotations

"""SQLAlchemy model for per-customer LLM provider configuration."""

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, JSON, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin
from backend.models.enums import LLMProviderEnum

if TYPE_CHECKING:
    from backend.models.customer import Customer


class LLMConnection(UUIDMixin, TimestampMixin, Base):
    """Per-customer configuration for an LLM provider.

    Each row represents a named, encrypted set of credentials and model
    settings that can be used to drive AI analysis for a specific customer.
    One connection per customer may be marked ``is_default``; the service layer
    enforces that constraint (rather than a partial-unique index) to keep the
    migration simple.

    Attributes:
        customer_id: FK to the owning customer; cascades on delete.
        name: Human-readable label (unique per customer).
        provider: The LLM backend to use (e.g. ``"anthropic"``).
        model: Model identifier string in provider-specific format.
        endpoint_url: Optional base URL override; ``None`` uses the provider
            default.
        api_key_encrypted: Fernet-encrypted API key bytes; ``None`` when
            credentials come from environment variables or IAM roles.
        extra_config: Provider-specific JSON extras (e.g. AWS region, GCP
            project).
        is_default: When ``True``, this connection is used by default for the
            customer's scans.  The service layer ensures at most one per
            customer.
    """

    __tablename__ = "llm_connections"
    __table_args__ = (
        UniqueConstraint("customer_id", "name", name="uq_llm_connection_customer_name"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[LLMProviderEnum] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(String(512))
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    extra_config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    customer: Mapped[Customer] = relationship(
        "Customer",
        back_populates="llm_connections",
    )
