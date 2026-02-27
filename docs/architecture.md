# Architecture Overview

## System Design

The DevOps Discovery & Reporting Platform follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                        │
│              (Vite + TailwindCSS 4 SPA)                 │
├─────────────────────────────────────────────────────────┤
│                   FastAPI REST API                       │
│         /api/customers, /api/scans, /api/reports        │
├──────────┬──────────────┬──────────────┬────────────────┤
│ Provider │   Scanner    │    AI        │    Report      │
│  Layer   │   Engine     │  Analysis    │  Generator     │
├──────────┴──────────────┴──────────────┴────────────────┤
│              SQLAlchemy 2.0 (Async ORM)                 │
├─────────────────────────────────────────────────────────┤
│              PostgreSQL 17 (asyncpg)                    │
└─────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### Provider Layer (`backend/providers/`)

Abstracts platform-specific API interactions behind a common `PlatformProvider` protocol. Each provider implements:

- `validate_connection()` -- test that credentials are valid
- `list_repos()` -- enumerate repositories in an organization
- `get_repo_assessment_data(repo)` -- collect repository-level metadata
- `get_org_assessment_data()` -- collect organization-level metadata

The `create_provider()` factory in `factory.py` decrypts Fernet-encrypted credentials and instantiates the correct provider class.

**Implementations:**
- `GitHubProvider` -- fully implemented using PyGithub
- `GitLabProvider` -- stub (raises `NotImplementedError`)
- `AzureDevOpsProvider` -- stub (raises `NotImplementedError`)

### Scanner Engine (`backend/scanners/`)

Evaluates collected data against 169 checks across 16 domains. Two scanner protocols exist:

- `Scanner` -- repo-level scanners implementing `evaluate(RepoAssessmentData)`
- `OrgScanner` -- org-level scanners implementing `evaluate_org(OrgAssessmentData)`

The `ScanOrchestrator` coordinates all 16 scanners and produces unified scoring. See [Scanner Engine](scanner-engine.md) for details.

### AI Analysis (`backend/analysis/`)

Uses Claude Opus 4.6 to generate:
- Executive summary prose
- Per-category narrative analysis (strengths, weaknesses, key findings)
- Prioritized recommendations with effort/impact ratings
- Benchmark comparison summaries

The `DevOpsAnalyzer` prepares a structured prompt with all scan data and benchmark results, then parses Claude's JSON response into a Pydantic `AnalysisResult` schema.

### Report Generator (`backend/reports/`)

Produces PDF reports using:
1. **Jinja2 templates** -- 5 section templates stitched into a base layout
2. **WeasyPrint** -- converts the rendered HTML to PDF
3. **Inlined CSS** -- `report.css` is embedded directly in the HTML

### Services Layer (`backend/services/`)

Business logic that orchestrates the pipeline:
- `scan_service.py` -- manages the full scan lifecycle (see [Scan Workflow](scan-workflow.md))
- `report_service.py` -- manages report generation lifecycle
- `customer_service.py` -- customer and connection CRUD
- `secrets_service.py` -- Fernet encryption/decryption for credentials at rest

## Data Flow

### Scan Flow

```
POST /api/customers/{id}/scans
        │
        ▼
  Create Scan (status=pending)
        │
        ▼
  Background Task: run_scan()
        │
        ├── 1. Load scan + connection
        ├── 2. Create provider (decrypt credentials)
        ├── 3. Fetch org assessment data
        ├── 4. Run org-level scanners (2 scanners, 23 checks)
        ├── 5. List repositories
        ├── 6. For each repo:
        │      ├── Fetch repo assessment data
        │      ├── Run repo-level scanners (14 scanners, 146 checks)
        │      └── Persist findings
        ├── 7. Calculate category scores
        └── 8. Mark scan complete
```

### Report Flow

```
POST /api/scans/{id}/reports
        │
        ▼
  Create Report (status=pending)
        │
        ▼
  Background Task: generate_report_for_scan()
        │
        ├── 1. Load findings + scores from DB
        ├── 2. Compute benchmarks (DORA, OpenSSF, SLSA, CIS)
        ├── 3. AI analysis (Claude Opus 4.6)
        ├── 4. Render HTML from Jinja2 templates
        ├── 5. Generate PDF via WeasyPrint
        └── 6. Persist report metadata + PDF path
```

## Configuration

All configuration is via environment variables, loaded through Pydantic Settings:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `ANTHROPIC_API_KEY` | Yes | Claude API key for AI analysis |
| `CREDENTIALS_ENCRYPTION_KEY` | Yes | Fernet key for credential encryption |
| `REPORTS_DIR` | No | PDF output directory (default: `./reports`) |
| `HOST` | No | Server bind host (default: `0.0.0.0`) |
| `PORT` | No | Server bind port (default: `8000`) |

## Async Architecture

The entire backend is async:
- **asyncpg** -- native PostgreSQL async driver
- **SQLAlchemy 2.0 async sessions** -- `async_sessionmaker` throughout
- **PyGithub blocking calls** -- wrapped in `asyncio.run_in_executor()` via the provider's `_run()` helper
- **Background tasks** -- scan and report generation run as `asyncio.Task` instances, returning immediately to the caller
