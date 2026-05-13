from __future__ import annotations

"""SQLAlchemy model for per-customer remediation policy configuration."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.customer import Customer


class RemediationPolicy(UUIDMixin, TimestampMixin, Base):
    """Per-customer policy controlling the agent remediation runtime.

    Exactly one row per customer (UniqueConstraint on customer_id).
    Default values match the safest defaults — enabled=False, auto_dispatch=False,
    kill_switch_enabled=False — so a brand-new customer is opt-in only.

    Attributes:
        customer_id: FK to the owning customer; cascades on delete.
        enabled: Master toggle — when False the remediation agent will not act
            on any findings regardless of other settings.
        auto_dispatch: When True, a remediation AgentRun is automatically
            created and triggered after each completed scan.
        kill_switch_enabled: Emergency stop — overrides ``auto_dispatch``; when
            True no agent runs will be dispatched even if ``auto_dispatch`` is True.
        allowed_check_ids: Explicit allowlist of check IDs the agent may act on.
            An empty list means *all* checks are allowed (subject to
            ``blocked_check_ids``).
        blocked_check_ids: Explicit denylist of check IDs the agent must never
            touch.  Takes precedence over ``allowed_check_ids``.
        max_prs_per_scan: Upper bound on the number of pull requests the agent
            may open per scan run.
        max_cost_usd_per_month: Soft monthly LLM-cost cap in USD; the agent
            runner checks this before each invocation.
        allowed_path_globs: Glob patterns restricting which paths the agent may
            modify (e.g. ``["src/**", "tests/**"]``).  Empty list means all
            paths are allowed.
        denied_path_globs: Glob patterns explicitly excluded from agent
            modifications.  Takes precedence over ``allowed_path_globs``.
        runtime_mode: Where the agent runs — ``"backend"`` (in-process) or
            ``"ci"`` (via CI pipeline injection).
        oversight_mode: Human-in-the-loop mode — ``"strict"`` (PR review
            required before merge) or ``"standard"`` (agent may auto-merge
            low-risk fixes).
        llm_input_scope: How much code context is passed to the LLM per call —
            ``"hunk"`` (diff hunk only), ``"file"`` (whole file), or
            ``"repo-context"`` (repo-level context window).
    """

    __tablename__ = "remediation_policies"
    __table_args__ = (UniqueConstraint("customer_id", name="uq_remediation_policy_customer"),)

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    auto_dispatch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    kill_switch_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    allowed_check_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    blocked_check_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    max_prs_per_scan: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )
    max_cost_usd_per_month: Mapped[float] = mapped_column(
        Float, nullable=False, default=100.0, server_default="100.0"
    )
    allowed_path_globs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    denied_path_globs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    runtime_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="backend", server_default="'backend'"
    )
    oversight_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="strict", server_default="'strict'"
    )
    llm_input_scope: Mapped[str] = mapped_column(
        String(16), nullable=False, default="hunk", server_default="'hunk'"
    )
    ci_workflow_repo: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ci_workflow_ref: Mapped[str] = mapped_column(
        String(128), nullable=False, default="main", server_default="'main'"
    )

    # Relationships
    customer: Mapped[Customer] = relationship(
        "Customer",
        back_populates="remediation_policy",
    )
