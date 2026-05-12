from __future__ import annotations

"""SQLAlchemy models for the remediation agent runtime.

Three tables:
  - agent_runs      — one row per invocation of the remediation agent.
  - agent_steps     — ordered trace of LLM calls, tool calls, and observations.
  - remediation_actions — per-finding PR outcomes produced during a run.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin
from backend.models.enums import AgentRunStatus, AgentStepType, RemediationActionStatus

if TYPE_CHECKING:
    from backend.models.finding import Finding
    from backend.models.llm import LLMConnection
    from backend.models.scan import Scan


class AgentRun(UUIDMixin, TimestampMixin, Base):
    """A single invocation of the remediation agent against a completed scan.

    Each row tracks the full lifecycle of one agent execution: which scan was
    remediated, which LLM connection was used, token and cost accounting, and
    the final status.  The ``callback_secret`` column stores an HMAC secret
    for CI-mode webhook verification (Phase 4); it is populated at insert time
    even though it is only consumed in Phase 4.

    Attributes:
        scan_id: FK to the scan being remediated; cascades on delete.
        llm_connection_id: FK to the LLM config used for this run; restricted
            from deletion while runs reference it.
        provider: LLM provider string snapshot (denormalised for reporting).
        model: Model identifier snapshot (denormalised for reporting).
        status: Current lifecycle state of the run.
        started_at: Wall-clock time when the agent began executing.
        finished_at: Wall-clock time when the run reached a terminal state.
        total_input_tokens: Cumulative prompt tokens across all steps.
        total_output_tokens: Cumulative completion tokens across all steps.
        total_cost_usd: Cumulative API cost in US dollars.
        error: Human-readable error message when ``status == "failed"``.
        runtime_mode: Execution context; ``"backend"`` (default) or ``"ci"``.
        callback_secret: 32-byte HMAC secret for CI-mode webhook signatures.
    """

    __tablename__ = "agent_runs"

    scan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    llm_connection_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("llm_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        String(32),
        nullable=False,
        default=AgentRunStatus.pending,
        server_default=AgentRunStatus.pending.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    runtime_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="backend", server_default="backend"
    )
    callback_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Relationships
    scan: Mapped[Scan] = relationship("Scan", back_populates="agent_runs")
    llm_connection: Mapped[LLMConnection] = relationship(
        "LLMConnection", back_populates="agent_runs"
    )
    steps: Mapped[list[AgentStep]] = relationship(
        "AgentStep",
        back_populates="agent_run",
        cascade="all, delete-orphan",
        order_by="AgentStep.step_index",
    )
    actions: Mapped[list[RemediationAction]] = relationship(
        "RemediationAction",
        back_populates="agent_run",
        cascade="all, delete-orphan",
    )


class AgentStep(UUIDMixin, TimestampMixin, Base):
    """One recorded step in an agent run's execution trace.

    Steps are stored in insertion order via ``step_index``, which is monotonic
    per run.  The unique constraint ``uq_agent_steps_run_index`` prevents
    duplicate indices within a single run.

    Sensitive values (API keys embedded in args, secret tokens in results) must
    be redacted by the service layer before persisting to
    ``tool_args_redacted`` and ``tool_result_redacted``.

    Attributes:
        agent_run_id: FK to the owning run; cascades on delete.
        step_index: Zero-based monotonic counter; unique per run.
        step_type: Categorises the step (LLM call, tool call, etc.).
        prompt_hash: SHA-256 hex digest of the prompt sent to the LLM; ``None``
            for non-LLM steps.
        tool_name: Name of the tool invoked; ``None`` for LLM steps.
        tool_args_redacted: Sanitised JSON representation of tool arguments.
        tool_result_redacted: Sanitised plain-text tool result.
        input_tokens: Prompt tokens consumed in this step (0 for non-LLM steps).
        output_tokens: Completion tokens produced in this step.
        latency_ms: Wall-clock duration of the step in milliseconds.
        status: Outcome string (e.g. ``"ok"``, ``"error"``).
    """

    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "step_index", name="uq_agent_steps_run_index"),
    )

    agent_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[AgentStepType] = mapped_column(String(32), nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    tool_name: Mapped[str | None] = mapped_column(String(255))
    tool_args_redacted: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    tool_result_redacted: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")

    # Relationships
    agent_run: Mapped[AgentRun] = relationship("AgentRun", back_populates="steps")


class RemediationAction(UUIDMixin, TimestampMixin, Base):
    """A pull-request action raised by the agent for a specific finding.

    One row is created for each check the agent attempts to remediate.  When
    the agent opens a PR, ``pr_url`` and ``branch`` are populated and
    ``status`` transitions to ``"opened"``.

    Attributes:
        agent_run_id: FK to the owning run; cascades on delete.
        finding_id: FK to the finding being remediated; cascades on delete.
        check_id: Domain-prefixed check identifier snapshot (e.g. ``CICD-008``).
        pr_url: URL of the pull request opened by the agent; ``None`` until
            the PR is created.
        branch: Git branch name used for the patch; ``None`` until created.
        status: Current state of the remediation action.
        opened_at: Timestamp when the PR was opened.
        merged_at: Timestamp when the PR was merged.
    """

    __tablename__ = "remediation_actions"

    agent_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    finding_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
    )
    check_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pr_url: Mapped[str | None] = mapped_column(String(512))
    branch: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[RemediationActionStatus] = mapped_column(
        String(32),
        nullable=False,
        default=RemediationActionStatus.planned,
        server_default=RemediationActionStatus.planned.value,
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    agent_run: Mapped[AgentRun] = relationship("AgentRun", back_populates="actions")
    finding: Mapped[Finding] = relationship("Finding", back_populates="remediation_actions")
