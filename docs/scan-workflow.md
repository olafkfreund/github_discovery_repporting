# Scan Workflow

## Overview

A scan is the core operation of the platform. It collects data from a connected platform (GitHub), runs all 16 scanners, computes scores, and persists the results. The entire process runs asynchronously in the background.

## Trigger

```
POST /api/customers/{customer_id}/scans
Body: { "connection_id": "<uuid>" }
```

The API validates that the customer and connection exist and belong together, creates a `Scan` record with `status=pending`, and immediately returns the scan ID. The actual work happens in a background `asyncio.Task`.

## Pipeline Steps

### Step 1: Load Scan and Connection

Load the `Scan` ORM object with its associated `PlatformConnection` via `selectinload`. Transition status to `scanning` and record `started_at`.

### Step 2: Create Provider

Call `create_provider(connection)` which:
1. Decrypts the Fernet-encrypted credentials blob
2. Parses the JSON credentials
3. Instantiates the correct provider class (e.g., `GitHubProvider`)

### Step 3: Validate Connection

Call `await provider.validate_connection()` to confirm credentials are still valid before proceeding.

### Step 4: Org-Level Scanning

```
org_data = await provider.get_org_assessment_data()
org_results = orchestrator.scan_org(org_data)
```

This runs the two org-level scanners:
- **PlatformArchScanner** (11 checks) -- evaluates org security settings, billing plan, default visibility
- **IdentityAccessScanner** (12 checks) -- evaluates MFA, SSO, admin ratio, RBAC

Org-level findings are persisted with `scan_repo_id=None` since they are not tied to any specific repository.

If org-level scanning fails (e.g., insufficient permissions), the error is logged as a warning and the pipeline continues with repo-level scanning.

### Step 5: List Repositories

```
repos = await provider.list_repos()
```

Returns a list of `NormalizedRepo` objects with standardized fields (name, URL, default branch, language, topics, etc.).

### Step 6: Per-Repository Scanning

For each repository:

1. **Fetch assessment data:**
   ```
   assessment = await provider.get_repo_assessment_data(repo)
   ```
   This collects branch protection rules, CI workflows, security features, file presence flags (Dockerfile, IaC, monitoring configs, etc.), and recent PR data.

2. **Create ScanRepo record** -- links the repository to the scan with its metadata.

3. **Run all 14 repo-level scanners:**
   ```
   repo_results = orchestrator.scan_repo(assessment)
   ```
   Each scanner evaluates its checks against the assessment data and returns `CheckResult` objects.

4. **Persist findings** -- each `CheckResult` becomes a `Finding` row in the database with the check ID, status, detail, evidence, score, and severity.

### Step 7: Calculate Scores

After all repositories are scanned:

```
all_results = org_results + all_repo_results
category_scores = orchestrator.calculate_category_scores(all_results)
overall_score = orchestrator.calculate_overall_score(category_scores)
```

One `ScanScore` row is persisted per category (16 total), recording the earned score, max score, weight, finding count, pass count, and fail count.

### Step 8: Complete

Set `scan.status = completed`, record `completed_at` and `total_repos`. Commit all changes.

## Error Handling

If any unhandled exception occurs during the pipeline:
- The scan status is set to `failed`
- The error message is recorded in `scan.error_message`
- The transaction is committed to preserve the error state

Org-level scanning failures are non-fatal -- the pipeline logs a warning and continues with repo scanning.

## Status Transitions

```
pending → scanning → completed
                  └→ failed
```

## Data Collected by GitHub Provider

### Organization Level (`get_org_assessment_data`)

| Data Point | Source |
|-----------|--------|
| Member count | `org.get_members()` |
| Admin count | `org.get_members(role="admin")` |
| MFA enforcement | `org.two_factor_requirement_enabled` |
| Default repo permission | `org.default_repository_permission` |
| Public repo creation | `org.members_can_create_public_repositories` |
| Billing plan | `org.plan.name` |
| Org security policy | `.github` repo `SECURITY.md` check |

### Repository Level (`get_repo_assessment_data`)

| Data Point | Source |
|-----------|--------|
| Branch protection | `branch.get_protection()` -- review count, admin enforcement, force push, signed commits |
| CI workflows | `.github/workflows/*.yml` -- trigger events, test/lint/security/deploy step detection |
| Workflow runs | `workflow.get_runs()` -- status, conclusion, duration |
| Security features | Dependabot, secret scanning, code scanning, vulnerability alerts |
| File presence | ~36 candidate paths checked for Dockerfiles, IaC, monitoring, SAST, docs, etc. |
| Recent PRs | `repo.get_pulls()` -- additions, deletions, review count, merge status |
| SBOM | Dependency graph SBOM endpoint |
