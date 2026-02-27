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

- `backend/providers/` - Platform abstraction with normalized models
- `backend/scanners/` - Five category scanners (Security 40%, CI/CD 20%, Code Quality 20%, Collab 10%, Governance 10%)
- `backend/analysis/` - Claude AI integration with structured outputs
- `backend/reports/` - WeasyPrint PDF generation from Jinja2 templates

## Key Conventions

- All models use UUID primary keys with timestamp mixins
- Platform credentials encrypted with Fernet before DB storage
- Async throughout (asyncpg, async SQLAlchemy sessions)
- Pydantic schemas for all API request/response models
- No authentication (internal network tool)
