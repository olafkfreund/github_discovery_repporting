"""Add has_write_scope nullable boolean column to platform_connections.

Revision ID: 005_add_write_scope_flag
Revises: 004_add_llm_connections
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005_add_write_scope_flag"
down_revision = "004_add_llm_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add has_write_scope column to platform_connections table."""
    op.add_column(
        "platform_connections",
        sa.Column("has_write_scope", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    """Remove has_write_scope column from platform_connections table."""
    op.drop_column("platform_connections", "has_write_scope")
