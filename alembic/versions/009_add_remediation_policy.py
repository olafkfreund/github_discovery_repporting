"""Add remediation_policies table.

Revision ID: 009_add_remediation_policy
Revises: 008_add_skills_and_profiles
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "009_add_remediation_policy"
down_revision = "008_add_skills_and_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the remediation_policies table with a unique constraint per customer."""
    op.create_table(
        "remediation_policies",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "customer_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_dispatch", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "kill_switch_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("allowed_check_ids", sa.JSON(), nullable=False),
        sa.Column("blocked_check_ids", sa.JSON(), nullable=False),
        sa.Column(
            "max_prs_per_scan", sa.Integer(), nullable=False, server_default="10"
        ),
        sa.Column(
            "max_cost_usd_per_month", sa.Float(), nullable=False, server_default="100.0"
        ),
        sa.Column("allowed_path_globs", sa.JSON(), nullable=False),
        sa.Column("denied_path_globs", sa.JSON(), nullable=False),
        sa.Column(
            "runtime_mode", sa.String(16), nullable=False, server_default="backend"
        ),
        sa.Column(
            "oversight_mode", sa.String(16), nullable=False, server_default="strict"
        ),
        sa.Column(
            "llm_input_scope", sa.String(16), nullable=False, server_default="hunk"
        ),
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
    op.create_unique_constraint(
        "uq_remediation_policy_customer",
        "remediation_policies",
        ["customer_id"],
    )


def downgrade() -> None:
    """Drop the remediation_policies table and its unique constraint."""
    op.drop_constraint(
        "uq_remediation_policy_customer", "remediation_policies", type_="unique"
    )
    op.drop_table("remediation_policies")
