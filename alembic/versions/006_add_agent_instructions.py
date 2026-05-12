"""Add agent_instructions table + agent_instructions_override on platform_connections.

Revision ID: 006_add_agent_instructions
Revises: 005_add_write_scope_flag
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_add_agent_instructions"
down_revision = "005_add_write_scope_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create agent_instructions table and add override column to platform_connections."""
    op.create_table(
        "agent_instructions",
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
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
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
    op.create_index(
        "ix_agent_instructions_customer_id",
        "agent_instructions",
        ["customer_id"],
    )
    op.create_unique_constraint(
        "uq_agent_instructions_customer_id",
        "agent_instructions",
        ["customer_id"],
    )
    op.add_column(
        "platform_connections",
        sa.Column("agent_instructions_override", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove agent_instructions table and override column from platform_connections."""
    op.drop_column("platform_connections", "agent_instructions_override")
    op.drop_constraint(
        "uq_agent_instructions_customer_id",
        "agent_instructions",
        type_="unique",
    )
    op.drop_index("ix_agent_instructions_customer_id", table_name="agent_instructions")
    op.drop_table("agent_instructions")
