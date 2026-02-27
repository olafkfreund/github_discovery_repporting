"""Expand category enum to 16 domains and make findings.scan_repo_id nullable.

Revision ID: 001_expand_categories
Revises: None
Create Date: 2026-02-27
"""

from __future__ import annotations

from alembic import op

revision = "001_expand_categories"
down_revision = None
branch_labels = None
depends_on = None

# New category enum values to add (the old 5 are removed/replaced).
_OLD_VALUES = ("security", "governance")
_NEW_VALUES = (
    "platform_arch",
    "identity_access",
    "repo_governance",
    "secrets_mgmt",
    "dependencies",
    "sast",
    "dast",
    "container_security",
    "sdlc_process",
    "compliance",
    "disaster_recovery",
    "monitoring",
    "migration",
)


def upgrade() -> None:
    # Add new enum values to the category type.
    # PostgreSQL enums are extended with ALTER TYPE ... ADD VALUE.
    for value in _NEW_VALUES:
        op.execute(f"ALTER TYPE category ADD VALUE IF NOT EXISTS '{value}'")

    # Make scan_repo_id nullable for org-level findings.
    op.alter_column(
        "findings",
        "scan_repo_id",
        nullable=True,
    )


def downgrade() -> None:
    # Make scan_repo_id non-nullable again (requires removing any NULL rows first).
    op.execute("DELETE FROM findings WHERE scan_repo_id IS NULL")
    op.alter_column(
        "findings",
        "scan_repo_id",
        nullable=False,
    )
    # Note: PostgreSQL does not support removing values from an enum type.
    # A full downgrade would require recreating the enum, which is complex
    # and rarely needed. The old values (security, governance) are kept
    # but unused by the application code.
