"""Add agent_runs, agent_steps, and remediation_actions tables.

Revision ID: 007_add_agent_runtime_tables
Revises: 006_add_agent_instructions
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_add_agent_runtime_tables"
down_revision = "006_add_agent_instructions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create agent_runs, agent_steps, and remediation_actions tables."""
    # ------------------------------------------------------------------
    # agent_runs
    # ------------------------------------------------------------------
    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "scan_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "llm_connection_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llm_connections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "runtime_mode",
            sa.String(32),
            nullable=False,
            server_default="backend",
        ),
        sa.Column("callback_secret", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_runs_scan_id", "agent_runs", ["scan_id"])
    op.create_index("ix_agent_runs_llm_connection_id", "agent_runs", ["llm_connection_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])

    # ------------------------------------------------------------------
    # agent_steps
    # ------------------------------------------------------------------
    op.create_table(
        "agent_steps",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "agent_run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(32), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("tool_name", sa.String(255), nullable=True),
        sa.Column("tool_args_redacted", sa.JSON(), nullable=True),
        sa.Column("tool_result_redacted", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ok"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("agent_run_id", "step_index", name="uq_agent_steps_run_index"),
    )
    op.create_index("ix_agent_steps_agent_run_id", "agent_steps", ["agent_run_id"])

    # ------------------------------------------------------------------
    # remediation_actions
    # ------------------------------------------------------------------
    op.create_table(
        "remediation_actions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "agent_run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("findings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("check_id", sa.String(64), nullable=False),
        sa.Column("pr_url", sa.String(512), nullable=True),
        sa.Column("branch", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="planned",
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_remediation_actions_agent_run_id", "remediation_actions", ["agent_run_id"])
    op.create_index("ix_remediation_actions_finding_id", "remediation_actions", ["finding_id"])


def downgrade() -> None:
    """Drop agent_runs, agent_steps, and remediation_actions tables."""
    op.drop_index("ix_remediation_actions_finding_id", table_name="remediation_actions")
    op.drop_index("ix_remediation_actions_agent_run_id", table_name="remediation_actions")
    op.drop_table("remediation_actions")

    op.drop_index("ix_agent_steps_agent_run_id", table_name="agent_steps")
    op.drop_table("agent_steps")

    op.drop_index("ix_agent_runs_created_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_llm_connection_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_scan_id", table_name="agent_runs")
    op.drop_table("agent_runs")
