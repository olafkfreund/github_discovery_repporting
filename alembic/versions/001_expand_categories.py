"""Initial schema with 16-domain category enum.

Creates all tables for the DevOps Discovery platform including the
full 16-domain category enum, nullable scan_repo_id for org-level
findings, and all supporting tables.

Revision ID: 001_expand_categories
Revises: None
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "001_expand_categories"
down_revision = None
branch_labels = None
depends_on = None

# ── Enum definitions (raw SQL avoids async lifecycle bugs) ───────────

_PLATFORM_VALUES = ("github", "gitlab", "azure_devops")
_AUTH_TYPE_VALUES = ("token", "oauth", "pat")
_CATEGORY_VALUES = (
    "platform_arch", "identity_access", "repo_governance", "cicd",
    "secrets_mgmt", "dependencies", "sast", "dast",
    "container_security", "code_quality", "sdlc_process", "compliance",
    "collaboration", "disaster_recovery", "monitoring", "migration",
)
_SEVERITY_VALUES = ("critical", "high", "medium", "low", "info")
_CHECK_STATUS_VALUES = ("passed", "failed", "warning", "not_applicable", "error")
_SCAN_STATUS_VALUES = ("pending", "scanning", "analyzing", "generating_report", "completed", "failed")
_REPORT_STATUS_VALUES = ("pending", "generating", "completed", "failed")


def _create_enum_sql(name: str, values: tuple[str, ...]) -> str:
    vals = ", ".join(f"'{v}'" for v in values)
    return f"CREATE TYPE {name} AS ENUM ({vals})"


def upgrade() -> None:
    # Create enum types via raw SQL to avoid SQLAlchemy async lifecycle issues
    conn = op.get_bind()
    conn.execute(sa.text(_create_enum_sql("platform", _PLATFORM_VALUES)))
    conn.execute(sa.text(_create_enum_sql("authtype", _AUTH_TYPE_VALUES)))
    conn.execute(sa.text(_create_enum_sql("category", _CATEGORY_VALUES)))
    conn.execute(sa.text(_create_enum_sql("severity", _SEVERITY_VALUES)))
    conn.execute(sa.text(_create_enum_sql("checkstatus", _CHECK_STATUS_VALUES)))
    conn.execute(sa.text(_create_enum_sql("scanstatus", _SCAN_STATUS_VALUES)))
    conn.execute(sa.text(_create_enum_sql("reportstatus", _REPORT_STATUS_VALUES)))

    # Reusable column-type references (create_type=False: already created above)
    platform_col = PG_ENUM(*_PLATFORM_VALUES, name="platform", create_type=False)
    authtype_col = PG_ENUM(*_AUTH_TYPE_VALUES, name="authtype", create_type=False)
    category_col = PG_ENUM(*_CATEGORY_VALUES, name="category", create_type=False)
    severity_col = PG_ENUM(*_SEVERITY_VALUES, name="severity", create_type=False)
    checkstatus_col = PG_ENUM(*_CHECK_STATUS_VALUES, name="checkstatus", create_type=False)
    scanstatus_col = PG_ENUM(*_SCAN_STATUS_VALUES, name="scanstatus", create_type=False)
    reportstatus_col = PG_ENUM(*_REPORT_STATUS_VALUES, name="reportstatus", create_type=False)

    # customers
    op.create_table(
        "customers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("slug", sa.String, nullable=False, unique=True, index=True),
        sa.Column("contact_email", sa.String, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # platform_connections
    op.create_table(
        "platform_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("platform", platform_col, nullable=False),
        sa.Column("display_name", sa.String, nullable=False),
        sa.Column("base_url", sa.String, nullable=True),
        sa.Column("auth_type", authtype_col, nullable=False),
        sa.Column("credentials_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("org_or_group", sa.String, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # scans
    op.create_table(
        "scans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("connection_id", UUID(as_uuid=True), sa.ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", scanstatus_col, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_repos", sa.Integer, default=0),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("scan_config", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # scan_repos
    op.create_table(
        "scan_repos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_id", UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("repo_external_id", sa.String, nullable=False),
        sa.Column("repo_name", sa.String, nullable=False),
        sa.Column("repo_url", sa.String, nullable=False),
        sa.Column("default_branch", sa.String, nullable=True),
        sa.Column("raw_data", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # findings (scan_repo_id nullable for org-level findings)
    op.create_table(
        "findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_id", UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("scan_repo_id", UUID(as_uuid=True), sa.ForeignKey("scan_repos.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("category", category_col, nullable=False),
        sa.Column("check_id", sa.String, nullable=False),
        sa.Column("check_name", sa.String, nullable=False),
        sa.Column("severity", severity_col, nullable=False),
        sa.Column("status", checkstatus_col, nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("evidence", JSON, nullable=True),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # scan_scores
    op.create_table(
        "scan_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_id", UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("category", category_col, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("max_score", sa.Float, nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("finding_count", sa.Integer, nullable=False),
        sa.Column("pass_count", sa.Integer, nullable=False),
        sa.Column("fail_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # report_templates
    op.create_table(
        "report_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_default", sa.Boolean, default=False),
        sa.Column("header_logo_path", sa.String, nullable=True),
        sa.Column("accent_color", sa.String, default="#2563eb"),
        sa.Column("include_sections", JSON, nullable=True),
        sa.Column("custom_css", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # reports
    op.create_table(
        "reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_id", UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ai_summary", sa.Text, nullable=True),
        sa.Column("ai_recommendations", JSON, nullable=True),
        sa.Column("overall_score", sa.Float, nullable=True),
        sa.Column("dora_level", sa.String, nullable=True),
        sa.Column("pdf_path", sa.String, nullable=True),
        sa.Column("status", reportstatus_col, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("report_templates")
    op.drop_table("scan_scores")
    op.drop_table("findings")
    op.drop_table("scan_repos")
    op.drop_table("scans")
    op.drop_table("platform_connections")
    op.drop_table("customers")

    # Drop enum types
    conn = op.get_bind()
    for name in ("reportstatus", "scanstatus", "checkstatus", "severity", "category", "authtype", "platform"):
        conn.execute(sa.text(f"DROP TYPE IF EXISTS {name}"))
