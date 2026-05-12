"""Add profile_slug column to agent_instructions.

Revision ID: 008_add_profile_slug
Revises: 007_add_agent_runtime_tables
Create Date: 2026-05-12

Adds the ``profile_slug`` audit column introduced in issue #35.  The column
stores the slug of whichever built-in AGENTS.md profile was selected for a
customer (e.g. ``'standard'``, ``'banking'``, ``'public-sector'``,
``'strict'``).  Nullable so that existing rows and custom-instructions
customers are unaffected.

Migration coordination: if issue #34's migration also lands as ``008_*``,
one of the two migrations must be renumbered to ``009`` and its
``down_revision`` updated accordingly.  The integrator handles this at
merge time.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "008_add_profile_slug"
down_revision = "007_add_agent_runtime_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable profile_slug column to agent_instructions."""
    op.add_column(
        "agent_instructions",
        sa.Column("profile_slug", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    """Remove profile_slug column from agent_instructions."""
    op.drop_column("agent_instructions", "profile_slug")
