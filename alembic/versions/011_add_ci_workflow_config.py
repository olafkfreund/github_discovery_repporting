"""Add ci_workflow_repo and ci_workflow_ref columns to remediation_policies.

Revision ID: 011_add_ci_workflow_config
Revises: 010_add_settings
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011_add_ci_workflow_config"
down_revision = "010_add_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ci_workflow_repo and ci_workflow_ref columns to remediation_policies."""
    op.add_column(
        "remediation_policies",
        sa.Column("ci_workflow_repo", sa.String(512), nullable=True),
    )
    op.add_column(
        "remediation_policies",
        sa.Column(
            "ci_workflow_ref",
            sa.String(128),
            nullable=False,
            server_default="main",
        ),
    )


def downgrade() -> None:
    """Remove ci_workflow_repo and ci_workflow_ref columns."""
    op.drop_column("remediation_policies", "ci_workflow_ref")
    op.drop_column("remediation_policies", "ci_workflow_repo")
