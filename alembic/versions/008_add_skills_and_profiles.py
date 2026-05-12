"""Add skills, skill_toggles tables and extension columns.

Also pre-emptively adds agent_instructions.profile_slug for issue #35
so that sibling migration does not need a separate revision.

Revision ID: 008_add_skills_and_profiles
Revises: 007_add_agent_runtime_tables
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008_add_skills_and_profiles"
down_revision = "007_add_agent_runtime_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create skills and skill_toggles tables; add extension columns."""
    # ------------------------------------------------------------------
    # skills
    # ------------------------------------------------------------------
    op.create_table(
        "skills",
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
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("applies_to_check_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("triggers", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.UniqueConstraint("customer_id", "name", name="uq_skills_customer_name"),
    )
    op.create_index("ix_skills_customer_id", "skills", ["customer_id"])

    # ------------------------------------------------------------------
    # skill_toggles
    # ------------------------------------------------------------------
    op.create_table(
        "skill_toggles",
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
        sa.Column("skill_name", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.UniqueConstraint("customer_id", "skill_name", name="uq_skill_toggles"),
    )
    op.create_index("ix_skill_toggles_customer_id", "skill_toggles", ["customer_id"])

    # ------------------------------------------------------------------
    # Extension columns on existing tables
    # ------------------------------------------------------------------
    op.add_column(
        "platform_connections",
        sa.Column("skills_override", sa.JSON(), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("ai_enrichment", sa.JSON(), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column(
            "enable_scan_enrichment",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    # Pre-emptive: profile_slug for issue #35 (AgentInstructions profile slug).
    op.add_column(
        "agent_instructions",
        sa.Column("profile_slug", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    """Drop skills, skill_toggles tables and remove extension columns."""
    op.drop_column("agent_instructions", "profile_slug")
    op.drop_column("customers", "enable_scan_enrichment")
    op.drop_column("findings", "ai_enrichment")
    op.drop_column("platform_connections", "skills_override")

    op.drop_index("ix_skill_toggles_customer_id", table_name="skill_toggles")
    op.drop_table("skill_toggles")

    op.drop_index("ix_skills_customer_id", table_name="skills")
    op.drop_table("skills")
