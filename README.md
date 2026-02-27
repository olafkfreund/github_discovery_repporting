# DevOps Discovery & Reporting Platform

Multi-platform DevOps assessment tool that scans GitHub, GitLab, and Azure DevOps organizations, evaluates repositories against industry best practices across 16 security and operational domains, uses Claude AI for analysis, and generates comprehensive PDF reports.

## Features

- **16-Domain Scanner Engine** -- 169 automated checks across security, CI/CD, compliance, container security, SDLC process, and more
- **Multi-Platform Support** -- GitHub (implemented), GitLab and Azure DevOps (provider stubs ready)
- **Org + Repo Scanning** -- organization-level security posture assessment alongside per-repository analysis
- **Industry Benchmarks** -- automatic alignment scoring against OpenSSF Scorecard, SLSA, CIS Software Supply Chain, and DORA metrics
- **AI-Powered Analysis** -- Claude Opus 4.6 generates executive summaries, prioritized recommendations, and per-domain narratives
- **PDF Reports** -- professional assessment reports with executive summary, category breakdowns, benchmark comparisons, and full findings appendix
- **React Dashboard** -- real-time scan status, category score visualization, and findings filtering

## Architecture

```
                                    +------------------+
                                    |  React Frontend  |
                                    |  (Vite + TW 4)   |
                                    +--------+---------+
                                             |
                                    +--------v---------+
                                    |   FastAPI REST    |
                                    |   /api/...        |
                                    +--------+---------+
                                             |
              +------------------------------+-------------------------------+
              |                              |                               |
   +----------v----------+     +-------------v-----------+     +-------------v-----------+
   |   Provider Layer     |     |    Scanner Engine        |     |   Report Pipeline       |
   |                      |     |                          |     |                          |
   | GitHub / GitLab /    |     | 2 Org-level scanners     |     | AI Analysis (Claude)     |
   | Azure DevOps         |     | 14 Repo-level scanners   |     | Jinja2 Templates         |
   | (PlatformProvider)   |     | 169 total checks         |     | WeasyPrint PDF           |
   +----------+-----------+     +-------------+------------+     +-------------+------------+
              |                               |                                |
              +-------------------------------+--------------------------------+
                                              |
                                    +---------v---------+
                                    |  PostgreSQL 17    |
                                    |  (async via       |
                                    |   asyncpg)        |
                                    +-------------------+
```

## Quick Start

### Prerequisites

- [Nix](https://nixos.org/download) (recommended) or Python 3.12+, Node.js 22+, PostgreSQL 17
- Docker (for database)
- Anthropic API key (for AI analysis)

### Setup

```bash
# Clone and enter the project
git clone https://github.com/olafkfreund/github_discovery_repporting.git
cd github_discovery_repporting

# Option A: Nix (recommended)
nix develop

# Option B: Manual
# Ensure Python 3.12+, Node 22+, and PostgreSQL 17 are available

# Initialize everything
just setup           # Starts DB, installs deps, runs migrations

# Configure environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY and CREDENTIALS_ENCRYPTION_KEY
# Generate an encryption key: just gen-key
```

### Run

```bash
just dev             # Backend on http://localhost:8000
just fe-dev          # Frontend on http://localhost:5173
```

### Test

```bash
just test            # Run all tests
just test-cov        # Tests with coverage report
just check           # Lint + typecheck
```

## Scanner Domains

The engine evaluates repositories and organizations across 16 domains with weighted scoring:

| Domain | Weight | Checks | Scope | Check Prefix |
|--------|--------|--------|-------|-------------|
| Identity & Access | 10% | 12 | Org | IAM- |
| Repository Governance | 10% | 12 | Repo | REPO- |
| CI/CD Pipeline | 10% | 14 | Repo | CICD- |
| Secrets Management | 8% | 10 | Repo | SEC- |
| Dependency Management | 8% | 11 | Repo | DEP- |
| Platform Architecture | 6% | 11 | Org | PLAT- |
| SAST | 6% | 10 | Repo | SAST- |
| Container Security | 6% | 12 | Repo | CNTR- |
| Code Quality | 6% | 9 | Repo | CQ- |
| SDLC Process | 6% | 12 | Repo | SDLC- |
| Compliance & Audit | 6% | 11 | Repo | COMP- |
| Collaboration | 4% | 7 | Repo | COLLAB- |
| Disaster Recovery | 4% | 10 | Repo | DR- |
| Monitoring | 4% | 11 | Repo | MON- |
| DAST | 4% | 8 | Repo | DAST- |
| Migration Readiness | 2% | 9 | Repo | MIG- |

**Total: 169 checks, weights sum to 100%**

## Benchmark Frameworks

Scan results are automatically mapped to four industry frameworks:

- **DORA** -- classifies overall maturity as Elite / High / Medium / Low based on weighted score
- **OpenSSF Scorecard** -- maps 10 Scorecard categories to internal checks
- **SLSA** -- determines Supply-chain Levels (L1-L3) from build pipeline checks
- **CIS Software Supply Chain** -- evaluates 5 control domains for compliance percentage

## API Endpoints

| Group | Path | Description |
|-------|------|-------------|
| Health | `GET /api/health` | Liveness probe |
| Customers | `/api/customers/` | CRUD for assessment customers |
| Connections | `/api/customers/{id}/connections` | Platform credential management |
| Scans | `POST /api/customers/{id}/scans` | Trigger assessment scan |
| Findings | `GET /api/scans/{id}/findings` | Query scan results with filters |
| Scores | `GET /api/scans/{id}/scores` | Per-category score breakdown |
| Reports | `POST /api/scans/{id}/reports` | Generate AI-powered PDF report |
| Download | `GET /api/reports/{id}/download` | Stream PDF report |
| Dashboard | `/api/dashboard/stats` | Aggregate metrics |

Full API documentation: see `docs/api-reference.md`

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic |
| Database | PostgreSQL 17 (asyncpg driver) |
| AI | Anthropic Claude Opus 4.6 (structured outputs) |
| PDF | WeasyPrint + Jinja2 |
| Frontend | React 19, Vite, TailwindCSS 4 |
| Package mgr | uv (Python), npm (frontend) |
| Task runner | just |
| Dev env | Nix flake |

## Documentation

Detailed documentation is available in the `docs/` directory:

- [Architecture Overview](docs/architecture.md) -- system design, data flow, and component relationships
- [Scanner Engine](docs/scanner-engine.md) -- how the 16-domain scanner works, check scoring, and weight system
- [Scan Workflow](docs/scan-workflow.md) -- end-to-end scan pipeline from API trigger to completion
- [Report Generation](docs/report-generation.md) -- AI analysis, PDF templating, and benchmark integration
- [API Reference](docs/api-reference.md) -- complete endpoint documentation
- [Database Schema](docs/database-schema.md) -- all tables, relationships, and migration strategy

## Project Structure

```
backend/
  analysis/        # AI analysis pipeline (Claude integration)
  benchmarks/      # DORA, OpenSSF, SLSA, CIS mappings
  models/          # SQLAlchemy ORM models
  providers/       # Platform abstraction (GitHub, GitLab, Azure DevOps)
  reports/         # PDF generation (templates, styles, renderer)
  routers/         # FastAPI route handlers
  scanners/        # 16-domain scanner engine
  schemas/         # Pydantic request/response schemas
  services/        # Business logic (scan, report, secrets)
frontend/
  src/pages/       # React page components
  src/components/  # Shared layout components
  src/api/         # API client
tests/             # Pytest test suite
docs/              # Project documentation
```

## License

This project is proprietary software. All rights reserved.
