# CLAUDE.md - DevOps Discovery & Reporting Platform

## Overview

Multi-platform DevOps assessment tool that scans GitHub, GitLab, and Azure DevOps organizations, evaluates against industry best practices (OpenSSF, DORA, SLSA, CIS), uses Claude Opus 4.6 for analysis, and generates PDF reports.

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
FastAPI REST API -> Provider Layer (GitHub/GitLab/Azure) -> Scanner Engine -> AI Analyzer -> PDF Reports
```

### Provider Layer (`backend/providers/`)

Platform abstraction with normalized models. Implements `PlatformProvider` and `OrgScanner` protocols.
- `base.py` — Protocol definitions (`PlatformProvider`, `OrgScanner`)
- `factory.py` — Provider instantiation from encrypted connection credentials
- `github.py` — GitHub API via PyGithub (org + repo assessment data)
- `gitlab.py` — GitLab API via python-gitlab (fuzzy group resolution, safe attribute access)

### Scanner Engine (`backend/scanners/`)

16-domain scanner architecture with ~169 checks across org-level and repo-level scanners.

**Base class pattern** (`base.py`):
- `BaseScanner` provides shared `checks()`, cached `_check_map`, `_bool_check()`, and `_manual_review()` helpers
- All scanners inherit from `BaseScanner` to eliminate boilerplate
- `Scanner` protocol for repo-level, `OrgScanner` protocol for org-level

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
- `backend/reports/` — WeasyPrint PDF generation from Jinja2 templates
- `backend/benchmarks/` — OpenSSF, DORA, SLSA, CIS benchmark mappings

### Scan Pipeline

1. Provider fetches org-level assessment data
2. Org-level scanners run (platform_arch, identity_access)
3. Provider lists all repositories
4. Per-repo: fetch assessment data, run 14 repo-level scanners
5. Persist findings (org-level findings have `scan_repo_id=None`)
6. Compute per-category scores
7. AI analysis generates summary and recommendations
8. PDF report generated

## Key Conventions

- All models use UUID primary keys with `UUIDMixin` and `TimestampMixin`
- SQLAlchemy 2.0 `Mapped[]` types infer nullability — no explicit `nullable=` needed
- Platform credentials encrypted with Fernet before DB storage (`CREDENTIALS_ENCRYPTION_KEY` in `.env`)
- Async throughout (asyncpg, async SQLAlchemy sessions)
- Pydantic schemas for all API request/response models
- Scanner classes inherit from `BaseScanner` and use `_bool_check()`/`_manual_review()` helpers
- Check IDs use domain prefixes: PLAT-, IAM-, REPO-, CICD-, SEC-, DEP-, SAST-, DAST-, CNTR-, CQ-, SDLC-, COMP-, COLLAB-, DR-, MON-, MIG-
- No authentication (internal network tool)
