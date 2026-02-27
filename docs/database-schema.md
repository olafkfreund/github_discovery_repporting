# Database Schema

## Overview

The platform uses PostgreSQL 17 with SQLAlchemy 2.0 async ORM. All models use UUID primary keys (via `UUIDMixin`) and timezone-aware timestamps (via `TimestampMixin`).

## Entity Relationship Diagram

```
┌──────────────┐       ┌─────────────────────┐
│  customers   │───┐   │ platform_connections │
│              │   │   │                     │
│ id (PK)      │   └──>│ customer_id (FK)    │
│ name         │       │ platform            │
│ slug         │       │ credentials_encrypted│
│ contact_email│       │ org_or_group        │
└──────┬───────┘       └──────────┬──────────┘
       │                          │
       │       ┌──────────────────┘
       │       │
       ▼       ▼
┌──────────────────┐
│     scans        │
│                  │
│ id (PK)          │
│ customer_id (FK) │
│ connection_id(FK)│
│ status           │
│ total_repos      │
└───┬──────┬───────┘
    │      │
    │      │    ┌────────────────┐
    │      └───>│  scan_repos    │
    │           │                │
    │           │ id (PK)        │
    │           │ scan_id (FK)   │
    │           │ repo_name      │
    │           │ repo_url       │
    │           └───────┬────────┘
    │                   │
    ▼                   ▼
┌──────────────┐  ┌──────────────┐
│ scan_scores  │  │  findings    │
│              │  │              │
│ scan_id (FK) │  │ scan_id (FK) │
│ category     │  │ scan_repo_id │◄── nullable (org-level findings)
│ score        │  │ category     │
│ max_score    │  │ check_id     │
│ weight       │  │ status       │
└──────────────┘  │ severity     │
                  │ score        │
    ┌─────────┐   │ evidence     │
    │ reports │   └──────────────┘
    │         │
    │ scan_id │
    │ customer│
    │ pdf_path│
    │ ai_*    │
    └─────────┘
```

## Tables

### `customers`

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | UUID | PK, default uuid4 | |
| `name` | VARCHAR | NOT NULL | Customer display name |
| `slug` | VARCHAR | UNIQUE, NOT NULL, indexed | URL-friendly identifier |
| `contact_email` | VARCHAR | nullable | |
| `notes` | TEXT | nullable | |
| `created_at` | TIMESTAMP(tz) | server default | |
| `updated_at` | TIMESTAMP(tz) | server default, on update | |

### `platform_connections`

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | UUID | PK | |
| `customer_id` | UUID | FK -> customers, CASCADE | |
| `platform` | ENUM | NOT NULL | `github` / `gitlab` / `azure_devops` |
| `display_name` | VARCHAR | NOT NULL | |
| `base_url` | VARCHAR | nullable | Self-hosted instance URL |
| `auth_type` | ENUM | NOT NULL | `token` / `oauth` / `pat` |
| `credentials_encrypted` | BYTEA | NOT NULL | Fernet-encrypted JSON |
| `org_or_group` | VARCHAR | NOT NULL | Organization/group name |
| `is_active` | BOOLEAN | default true | |
| `last_validated_at` | TIMESTAMP(tz) | nullable | |

### `scans`

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | UUID | PK | |
| `customer_id` | UUID | FK -> customers, CASCADE | |
| `connection_id` | UUID | FK -> platform_connections, CASCADE | |
| `status` | ENUM | NOT NULL | `pending` / `scanning` / `completed` / `failed` |
| `started_at` | TIMESTAMP(tz) | nullable | |
| `completed_at` | TIMESTAMP(tz) | nullable | |
| `total_repos` | INTEGER | default 0 | |
| `error_message` | TEXT | nullable | Set on failure |
| `scan_config` | JSON | nullable | Caller-supplied configuration |

### `scan_repos`

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | UUID | PK | |
| `scan_id` | UUID | FK -> scans, CASCADE | |
| `repo_external_id` | VARCHAR | NOT NULL | Platform's native repo ID |
| `repo_name` | VARCHAR | NOT NULL | |
| `repo_url` | VARCHAR | NOT NULL | |
| `default_branch` | VARCHAR | nullable | |
| `raw_data` | JSON | nullable | Full NormalizedRepo dump |

### `findings`

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | UUID | PK | |
| `scan_id` | UUID | FK -> scans, CASCADE, indexed | |
| `scan_repo_id` | UUID | FK -> scan_repos, CASCADE, nullable, indexed | NULL for org-level findings |
| `category` | ENUM(16) | NOT NULL | One of 16 Category values |
| `check_id` | VARCHAR | NOT NULL | e.g., `REPO-001`, `IAM-003` |
| `check_name` | VARCHAR | NOT NULL | |
| `severity` | ENUM | NOT NULL | `critical` / `high` / `medium` / `low` / `info` |
| `status` | ENUM | NOT NULL | `passed` / `failed` / `warning` / `not_applicable` / `error` |
| `detail` | TEXT | nullable | Human-readable explanation |
| `evidence` | JSON | nullable | Structured supporting data |
| `weight` | FLOAT | NOT NULL | Scanner-defined check weight |
| `score` | FLOAT | NOT NULL | Computed: weight * status_multiplier |

**Key design decision:** `scan_repo_id` is nullable to support org-level findings (e.g., IAM checks, platform architecture checks) that are not associated with any specific repository.

### `scan_scores`

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | UUID | PK | |
| `scan_id` | UUID | FK -> scans, CASCADE | |
| `category` | ENUM(16) | NOT NULL | |
| `score` | FLOAT | NOT NULL | Earned score sum |
| `max_score` | FLOAT | NOT NULL | Possible score sum |
| `weight` | FLOAT | NOT NULL | Category weight (0.0-1.0) |
| `finding_count` | INTEGER | NOT NULL | Total checks evaluated |
| `pass_count` | INTEGER | NOT NULL | |
| `fail_count` | INTEGER | NOT NULL | |

### `reports`

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | UUID | PK | |
| `scan_id` | UUID | FK -> scans, CASCADE | |
| `customer_id` | UUID | FK -> customers, CASCADE | |
| `template_id` | UUID | FK -> report_templates, SET NULL | |
| `title` | VARCHAR | NOT NULL | |
| `generated_at` | TIMESTAMP(tz) | NOT NULL | |
| `ai_summary` | TEXT | nullable | Claude-generated executive summary |
| `ai_recommendations` | JSON | nullable | Structured recommendation list |
| `overall_score` | FLOAT | nullable | |
| `dora_level` | VARCHAR | nullable | `elite` / `high` / `medium` / `low` |
| `pdf_path` | VARCHAR | nullable | Relative path to PDF file |
| `status` | ENUM | NOT NULL | `pending` / `generating` / `completed` / `failed` |

### `report_templates`

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `id` | UUID | PK | |
| `name` | VARCHAR | NOT NULL | |
| `description` | TEXT | nullable | |
| `is_default` | BOOLEAN | default false | |
| `header_logo_path` | VARCHAR | nullable | |
| `accent_color` | VARCHAR | default `#2563eb` | |
| `include_sections` | JSON | nullable | List of section names to include |
| `custom_css` | TEXT | nullable | |

## Migrations

Migrations are managed with Alembic. The migration for the 16-domain expansion is at `alembic/versions/001_expand_categories.py` and:

1. Adds 11 new values to the `category` PostgreSQL enum type
2. Alters `findings.scan_repo_id` to `DROP NOT NULL`

### Running Migrations

```bash
just migrate            # Apply all pending migrations
just migrate-down       # Rollback the last migration
just migrate-create name  # Create a new auto-generated migration
```

## Credential Security

Platform credentials (API tokens, PATs) are encrypted at rest using Fernet symmetric encryption:

1. On storage: `secrets_service.encrypt(json.dumps(credentials))` -> stored as `BYTEA`
2. On retrieval: `secrets_service.decrypt(encrypted_bytes)` -> parsed back to dict
3. The encryption key is configured via `CREDENTIALS_ENCRYPTION_KEY` env var
4. Generate a key with `just gen-key`
