"""Add llm_connections table for per-customer LLM provider configuration.

Revision ID: 004_add_llm_connections
Revises: 003_add_export_paths
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "004_add_llm_connections"
down_revision = "003_add_export_paths"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the llm_connections table."""
    op.create_table(
        "llm_connections",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("endpoint_url", sa.String(512), nullable=True),
        sa.Column("api_key_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("extra_config", sa.JSON, nullable=True),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
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
        "uq_llm_connection_customer_name",
        "llm_connections",
        ["customer_id", "name"],
    )
    op.create_index(
        "ix_llm_connections_customer_id",
        "llm_connections",
        ["customer_id"],
    )


def downgrade() -> None:
    """Drop the llm_connections table."""
    op.drop_index("ix_llm_connections_customer_id", table_name="llm_connections")
    op.drop_constraint(
        "uq_llm_connection_customer_name",
        "llm_connections",
        type_="unique",
    )
    op.drop_table("llm_connections")
