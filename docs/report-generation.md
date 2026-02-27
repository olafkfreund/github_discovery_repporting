# Report Generation

## Overview

Report generation takes completed scan results and produces a comprehensive PDF assessment document. The pipeline has three stages: benchmark computation, AI analysis, and PDF rendering.

## Trigger

```
POST /api/scans/{scan_id}/reports
Body: { "title": "Assessment Report" }
```

Creates a `Report` record with `status=pending` and launches a background task. The API returns immediately with the report ID.

## Pipeline

### Stage 1: Data Preparation

1. Load all `Finding` rows for the scan from the database
2. Load all `ScanScore` rows for the scan
3. Reconstruct `CheckResult` objects from findings
4. Reconstruct `CategoryScore` objects from scan scores
5. Calculate the overall weighted score

### Stage 2: Benchmark Computation

Four industry benchmarks are evaluated against the set of passed check IDs:

#### DORA Performance Level

Maps the overall weighted score to a maturity band:

| Level | Score Range | Description |
|-------|------------|-------------|
| Elite | >= 85 | Multiple deploys per day |
| High | >= 70 | Daily to weekly deployments |
| Medium | >= 50 | Weekly to monthly deployments |
| Low | < 50 | Monthly to semi-annual deployments |

#### OpenSSF Scorecard Alignment

10 Scorecard categories are mapped to internal check IDs. A category is satisfied only when **all** mapped checks pass:

| Category | Required Checks |
|----------|----------------|
| Branch-Protection | REPO-001, REPO-002, REPO-003, REPO-005, REPO-006 |
| Code-Review | SDLC-003, REPO-002 |
| CI-Tests | CICD-001, CICD-003 |
| Vulnerabilities | DEP-002, DEP-003 |
| Dependency-Update-Tool | DEP-001 |
| Security-Policy | COMP-004 |
| Signed-Releases | REPO-007 |
| Token-Permissions | IAM-008 |
| SAST | CICD-005, SAST-001 |
| License | COMP-001 |

#### SLSA Build Level

Cumulative levels -- each requires all lower-level checks plus its own:

| Level | Required Checks |
|-------|----------------|
| L1 | CICD-001 |
| L2 | CICD-001, CICD-002 |
| L3 | CICD-001, CICD-002, CICD-012, REPO-005 |

#### CIS Software Supply Chain

5 control domains with partial compliance tracking:

| Domain | Required Checks |
|--------|----------------|
| Source Code | REPO-001, REPO-002, REPO-006, REPO-008 |
| Build Pipelines | CICD-001, CICD-003, CICD-005 |
| Dependencies | DEP-001, DEP-002, DEP-003 |
| Artifacts | DEP-009, REPO-007 |
| Deployment | CICD-006, CICD-007 |

### Stage 3: AI Analysis

The `DevOpsAnalyzer` sends scan data to Claude Opus 4.6:

**Input to Claude:**
- Category scores table (domain, percentage, pass/fail counts)
- Failed checks summary (ID, name, severity, detail)
- Passed checks summary
- Benchmark results (DORA level, OpenSSF alignment, SLSA level, CIS compliance)
- The expected JSON response schema (`AnalysisResult`)

**Output from Claude (`AnalysisResult`):**
- `executive_summary` -- 2-3 paragraph overview
- `overall_maturity` -- one-sentence maturity assessment
- `risk_highlights` -- top risk areas
- `category_narratives` -- per-domain analysis with strengths, weaknesses, key findings
- `recommendations` -- prioritized actions with effort/impact ratings and associated check IDs
- `benchmark_comparisons` -- framework-by-framework analysis

If AI analysis fails, a structured fallback is generated from the numeric data.

### Stage 4: PDF Rendering

#### Template Structure

Five Jinja2 templates are rendered and stitched into `base.html`:

| Template | Content |
|----------|---------|
| `executive_summary.html` | Cover page, overall score, DORA level, executive summary prose |
| `category_detail.html` | Per-category score bars and AI-generated narratives |
| `recommendations.html` | Prioritized action items with effort/impact labels |
| `benchmarks.html` | DORA, OpenSSF, SLSA, CIS compliance tables |
| `appendix.html` | Complete raw findings table grouped by category |

#### Styling

`report.css` is inlined into the HTML for WeasyPrint compatibility. It provides:
- Print-optimized layout with page break controls
- Score bar visualizations
- Severity-colored badges
- Table formatting
- Header/footer styling

#### PDF Output

WeasyPrint converts the rendered HTML to PDF. Output filename format:

```
{customer-slug}_{scan-id-short}_{YYYYMMDD}.pdf
```

The PDF is written to the configured `REPORTS_DIR` and the path is stored in the `Report` record.

## Status Transitions

```
pending → generating → completed
                    └→ failed
```

## Downloading Reports

```
GET /api/reports/{report_id}/download
```

Streams the PDF file with `Content-Type: application/pdf`.
