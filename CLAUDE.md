# CLAUDE.md - BPS-tool (DevOps Discovery & Reporting Platform)

## Overview

Multi-platform DevOps assessment tool that scans GitHub, GitLab, and Azure DevOps organizations, evaluates against industry best practices (OpenSSF, DORA, SLSA, CIS), uses Claude Opus 4.6 for analysis, and generates PDF reports.

**Frontend:** BPS-tool v1.0.1

## Tech Stack

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async + Alembic
- **Frontend:** React 19 + Vite + TailwindCSS 4
- **Database:** PostgreSQL 17 (asyncpg driver)
- **AI:** Anthropic Claude Opus 4.6 (structured outputs)
- **PDF:** WeasyPrint + Jinja2
- **Package mgr:** uv (Python), npm (frontend)
- **Task runner:** just
- **Dev env:** Nix flake

## Build & Run

```bash
nix develop                  # Enter dev shell
just setup                   # Start DB + install deps + run migrations
just dev                     # Start backend (port 8000)
just fe-dev                  # Start frontend (port 5173)
just test                    # Run tests
just check                   # Lint + typecheck
```

## Architecture

```
FastAPI REST API -> Provider Layer (GitHub/GitLab/Azure) -> Scanner Engine -> AI Analyzer -> PDF/Excel/Zip Reports
```

### Provider Layer (`backend/providers/`)

Platform abstraction with normalized models. Implements `PlatformProvider` and `OrgScanner` protocols.
- `base.py` — Protocol definitions (`PlatformProvider`, `OrgScanner`)
- `factory.py` — Provider instantiation from encrypted connection credentials
- `github.py` — GitHub API via PyGithub (org + repo assessment data)
- `gitlab.py` — GitLab API via python-gitlab (fuzzy group resolution, safe attribute access)
- `azure_devops.py` — Azure DevOps REST API v7.0 via httpx (async, PAT Basic auth, project:repo external_id encoding, tree-based file detection)

### Scanner Engine (`backend/scanners/`)

16-domain scanner architecture with ~169 checks across org-level and repo-level scanners.

**Base class pattern** (`base.py`):
- `BaseScanner` provides shared `checks()`, cached `_check_map`, `_bool_check()`, `_manual_review()`, and `_threshold()` helpers
- `_threshold(check_id, key, default)` reads per-check threshold overrides from scan profile config, falling back to the hardcoded default
- All scanners inherit from `BaseScanner` to eliminate boilerplate
- `Scanner` protocol for repo-level, `OrgScanner` protocol for org-level

**Scanner registry** (`registry.py`):
- `get_scanner_registry()` auto-generates metadata from scanner code (never manually maintained)
- `THRESHOLD_REGISTRY` maps 7 check IDs to tunable threshold key/default pairs (CICD-008, CICD-009, IAM-003, CQ-004, SDLC-003, SDLC-004, COLLAB-006)
- Returns `CategoryInfo` dataclasses with checks, weights, scopes, and threshold defaults for the API and frontend profile editor

**Orchestrator** (`orchestrator.py`):
- `ScanOrchestrator(scan_config=...)` accepts optional scan profile config
- Filters disabled categories/checks, overrides category weights, injects per-check threshold config
- Renormalises weights so enabled categories sum to 1.0
- `scan_org()` and `scan_repo()` filter out disabled check results

**16 scanner domains** (weights sum to 1.0):

| Domain | File | Weight | Scope | Checks |
|--------|------|--------|-------|--------|
| Platform Architecture | `platform_arch.py` | 0.06 | org | 11 |
| Identity & Access | `identity_access.py` | 0.10 | org | 12 |
| Repository Governance | `repo_governance.py` | 0.10 | repo | 12 |
| CI/CD Pipeline | `cicd.py` | 0.10 | repo | 14 |
| Secrets Management | `secrets_mgmt.py` | 0.08 | repo | 10 |
| Dependencies | `dependencies.py` | 0.08 | repo | 11 |
| SAST | `sast.py` | 0.06 | repo | 10 |
| DAST | `dast.py` | 0.04 | repo | 8 |
| Container Security | `container_security.py` | 0.06 | repo | 12 |
| Code Quality | `code_quality.py` | 0.06 | repo | 9 |
| SDLC Process | `sdlc_process.py` | 0.06 | repo | 12 |
| Compliance | `compliance.py` | 0.06 | repo | 11 |
| Collaboration | `collaboration.py` | 0.04 | repo | 7 |
| Disaster Recovery | `disaster_recovery.py` | 0.04 | repo | 10 |
| Monitoring | `monitoring.py` | 0.04 | repo | 11 |
| Migration Readiness | `migration.py` | 0.02 | repo | 9 |

### Analysis & Reports

- `backend/analysis/` — Claude AI integration with structured outputs, fallback scoring
- `backend/reports/` — Report generation (PDF, Excel, Markdown, Zip)
  - `backend/reports/pdf.py` — WeasyPrint PDF generation from Jinja2 templates
  - `backend/reports/excel.py` — ExcelRenderer: multi-sheet .xlsx workbook (Cover, Executive Summary, Category Scores, Recommendations, Benchmarks, All Findings)
  - `backend/reports/markdown.py` — MarkdownRenderer: 6 structured .md files for documentation/version control
  - `backend/reports/zip_bundler.py` — ZipBundler: packages Excel + Markdown into .zip archive
- `backend/benchmarks/` — OpenSSF, DORA, SLSA, CIS benchmark mappings

### Scan Profiles (`backend/models/scan_profile.py`, `backend/routers/scan_profiles.py`)

Per-customer scan profiles stored as JSON config, allowing users to:
- Toggle categories and individual checks on/off
- Override category weights
- Tune per-check thresholds (e.g. CICD-008 pass_threshold, IAM-003 max_admin_ratio)

Config is snapshotted into `Scan.scan_config` at scan trigger time for reproducibility. Profile schema uses sparse representation — absent categories/checks use defaults.

**API endpoints:**

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/scanners/registry` | All categories + checks with threshold defaults |
| GET | `/api/customers/{id}/scan-profiles` | List profiles for a customer |
| POST | `/api/customers/{id}/scan-profiles` | Create profile |
| GET | `/api/scan-profiles/{id}` | Get single profile |
| PUT | `/api/scan-profiles/{id}` | Update profile |
| DELETE | `/api/scan-profiles/{id}` | Delete profile |

**Report download endpoints:**

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/reports/{id}/download/excel` | Download Excel report |
| GET | `/api/reports/{id}/download/zip` | Download zip bundle (Excel + Markdown) |

**Frontend:** Profile editor at `/customers/:id/scan-profiles` with category toggles, weight inputs, check toggles, threshold editors, and weight summary. Profile selector in scan trigger form on CustomerDetailPage.

### Scan Pipeline

1. Provider fetches org-level assessment data
2. Org-level scanners run (platform_arch, identity_access)
3. Provider lists all repositories
4. Per-repo: fetch assessment data, run 14 repo-level scanners
5. Persist findings (org-level findings have `scan_repo_id=None`)
6. Compute per-category scores (filtered by scan profile config if present)
7. AI analysis generates summary and recommendations
7b. Excel report generated (multi-sheet workbook)
7c. Zip bundle generated (Excel + Markdown)
8. PDF, Excel, and Zip reports generated

## Key Conventions

- All models use UUID primary keys with `UUIDMixin` and `TimestampMixin`
- SQLAlchemy 2.0 `Mapped[]` types infer nullability — no explicit `nullable=` needed
- Platform credentials encrypted with Fernet before DB storage (`CREDENTIALS_ENCRYPTION_KEY` in `.env`)
- Async throughout (asyncpg, async SQLAlchemy sessions)
- Pydantic schemas for all API request/response models
- Scanner classes inherit from `BaseScanner` and use `_bool_check()`/`_manual_review()`/`_threshold()` helpers
- Check IDs use domain prefixes: PLAT-, IAM-, REPO-, CICD-, SEC-, DEP-, SAST-, DAST-, CNTR-, CQ-, SDLC-, COMP-, COLLAB-, DR-, MON-, MIG-
- Report model stores `pdf_path`, `excel_path`, and `zip_path` as relative paths under `REPORTS_DIR`
- No authentication (internal network tool)
