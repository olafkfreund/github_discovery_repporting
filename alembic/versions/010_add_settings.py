"""Add global settings singleton table.

Revision ID: 010_add_settings
Revises: 009_add_remediation_policy
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "010_add_settings"
down_revision = "009_add_remediation_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the settings table and insert the singleton row."""
    op.create_table(
        "settings",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "global_kill_switch_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "default_data_residency_region",
            sa.String(32),
            nullable=False,
            server_default="'eu-west'",
        ),
        sa.Column(
            "audit_log_retention_days",
            sa.Integer(),
            nullable=False,
            server_default="180",
        ),
        sa.Column(
            "streaming_log_retention_hours",
            sa.Integer(),
            nullable=False,
            server_default="72",
        ),
        sa.Column(
            "default_llm_connection_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
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
    # Insert the singleton row so every post-upgrade database has it.
    op.execute(
        sa.text(
            "INSERT INTO settings (id) VALUES ('00000000-0000-0000-0000-000000000001'::uuid)"
        )
    )


def downgrade() -> None:
    """Drop the settings table."""
    op.drop_table("settings")
