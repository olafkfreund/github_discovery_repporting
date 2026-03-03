"""Add excel_path and zip_path columns to reports table.

Revision ID: 003_add_export_paths
Revises: 002_add_scan_profiles
Create Date: 2026-03-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "003_add_export_paths"
down_revision = "002_add_scan_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("excel_path", sa.String(), nullable=True))
    op.add_column("reports", sa.Column("zip_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("reports", "zip_path")
    op.drop_column("reports", "excel_path")
