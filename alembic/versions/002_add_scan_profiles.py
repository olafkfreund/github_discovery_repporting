"""Add scan_profiles table and scans.profile_id FK.

Revision ID: 002_add_scan_profiles
Revises: 001_expand_categories
Create Date: 2026-03-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "002_add_scan_profiles"
down_revision = "001_expand_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_default", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("config", JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.add_column(
        "scans",
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("scan_profiles.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("scans", "profile_id")
    op.drop_table("scan_profiles")
