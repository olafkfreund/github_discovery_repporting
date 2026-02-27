# Scanner Engine

## Overview

The scanner engine evaluates organizations and repositories against 169 automated checks across 16 DevOps domains. It produces structured results that feed into scoring, benchmarking, AI analysis, and PDF reporting.

## Scanner Protocols

Two structural protocols define the scanner interface in `backend/scanners/base.py`:

### `Scanner` (repo-level)

```python
class Scanner(Protocol):
    category: Category
    weight: float

    def checks(self) -> list[ScanCheck]: ...
    def evaluate(self, data: RepoAssessmentData) -> list[CheckResult]: ...
```

### `OrgScanner` (org-level)

```python
class OrgScanner(Protocol):
    category: Category
    weight: float

    def checks(self) -> list[ScanCheck]: ...
    def evaluate_org(self, data: OrgAssessmentData) -> list[CheckResult]: ...
```

## Data Models

### ScanCheck

Metadata describing a single check:

| Field | Type | Description |
|-------|------|-------------|
| `check_id` | str | Unique identifier (e.g., `REPO-001`) |
| `check_name` | str | Human-readable name |
| `category` | Category | One of 16 domain categories |
| `severity` | Severity | `critical` / `high` / `medium` / `low` / `info` |
| `weight` | float | Scoring weight (default 1.0) |
| `description` | str | What this check evaluates |

### CheckResult

Outcome of evaluating one check:

| Field | Type | Description |
|-------|------|-------------|
| `check` | ScanCheck | The check that was evaluated |
| `status` | CheckStatus | `passed` / `failed` / `warning` / `not_applicable` / `error` |
| `detail` | str | Human-readable explanation |
| `evidence` | dict | Structured data supporting the result |
| `score` | float | Auto-computed from status and weight |

### Score Computation

Each check's score is automatically computed:

| Status | Score Formula |
|--------|--------------|
| `passed` | `weight * 1.0` |
| `warning` | `weight * 0.5` |
| `failed` | `0.0` |
| `error` | `0.0` |
| `not_applicable` | Excluded from max_score entirely |

## The 16 Scanner Domains

### Org-Level Scanners (2 scanners, 23 checks)

#### Platform Architecture (`PlatformArchScanner`)
- **Weight:** 0.06 | **Checks:** 11 | **Prefix:** PLAT-
- Evaluates org-level platform configuration: default repo visibility, IP allow-listing, advanced security features, audit logging, runner restrictions

#### Identity & Access (`IdentityAccessScanner`)
- **Weight:** 0.10 | **Checks:** 12 | **Prefix:** IAM-
- Evaluates authentication and authorization: MFA enforcement, SSO, admin ratio, RBAC, deploy key permissions, emergency access procedures

### Repo-Level Scanners (14 scanners, 146 checks)

#### Repository Governance (`RepoGovernanceScanner`)
- **Weight:** 0.10 | **Checks:** 12 | **Prefix:** REPO-
- Branch protection rules, PR review requirements, CODEOWNERS, signed commits, force push restrictions

#### CI/CD Pipeline (`CICDScanner`)
- **Weight:** 0.10 | **Checks:** 14 | **Prefix:** CICD-
- Pipeline existence, PR triggers, test/lint/security/deploy steps, success rate, build time, artifact signing, multi-environment support

#### Secrets Management (`SecretsMgmtScanner`)
- **Weight:** 0.08 | **Checks:** 10 | **Prefix:** SEC-
- Secret scanning, push protection, credential detection, vault usage, key rotation

#### Dependency Management (`DependenciesScanner`)
- **Weight:** 0.08 | **Checks:** 11 | **Prefix:** DEP-
- Dependabot/Renovate, vulnerability alerts, lock files, version pinning, SBOM generation, license compliance

#### SAST (`SASTScanner`)
- **Weight:** 0.06 | **Checks:** 10 | **Prefix:** SAST-
- Static analysis tool configuration, CI integration, CodeQL/Semgrep, critical findings, merge blocking

#### DAST (`DASTScanner`)
- **Weight:** 0.04 | **Checks:** 8 | **Prefix:** DAST-
- Dynamic security testing configuration, API testing, OWASP Top 10 coverage, authenticated scanning

#### Container Security (`ContainerSecurityScanner`)
- **Weight:** 0.06 | **Checks:** 12 | **Prefix:** CNTR-
- Dockerfile presence gates all other checks; evaluates base image trust, multi-stage builds, root user, image scanning, health checks

#### Code Quality (`CodeQualityScanner`)
- **Weight:** 0.06 | **Checks:** 9 | **Prefix:** CQ-
- Linter config, test framework, coverage tools, coverage threshold, EditorConfig, type checking

#### SDLC Process (`SDLCProcessScanner`)
- **Weight:** 0.06 | **Checks:** 12 | **Prefix:** SDLC-
- PR templates, contributing guide, review enforcement, PR size, branching strategy, release process, ADRs, API docs

#### Compliance & Audit (`ComplianceScanner`)
- **Weight:** 0.06 | **Checks:** 11 | **Prefix:** COMP-
- License file, audit logging, security policy, compliance frameworks, retention policy, change management

#### Collaboration (`CollaborationScanner`)
- **Weight:** 0.04 | **Checks:** 7 | **Prefix:** COLLAB-
- Issue templates, discussions, project boards, wiki, PR response time, stale management

#### Disaster Recovery (`DisasterRecoveryScanner`)
- **Weight:** 0.04 | **Checks:** 10 | **Prefix:** DR-
- Backup strategy, DR runbooks, IaC presence, multi-region capability, failover procedures

#### Monitoring & Observability (`MonitoringScanner`)
- **Weight:** 0.04 | **Checks:** 11 | **Prefix:** MON-
- Monitoring config, alerting rules, logging, tracing, SLO/SLA docs, on-call documentation, incident response playbooks

#### Migration Readiness (`MigrationScanner`)
- **Weight:** 0.02 | **Checks:** 9 | **Prefix:** MIG-
- Migration guides, API versioning, deprecation policy, database migration tools, environment parity

## ScanOrchestrator

The `ScanOrchestrator` class in `backend/scanners/orchestrator.py` coordinates all scanners:

```python
orchestrator = ScanOrchestrator()

# Org-level scanning
org_results = orchestrator.scan_org(org_data)

# Repo-level scanning
repo_results = orchestrator.scan_repo(repo_data)

# Combine and score
all_results = org_results + repo_results
category_scores = orchestrator.calculate_category_scores(all_results)
overall = orchestrator.calculate_overall_score(category_scores)
```

### Category Score Calculation

For each of the 16 categories:
1. Sum earned scores from all checks in that category
2. Sum max possible scores (excluding `not_applicable` checks)
3. Compute `percentage = (earned / max) * 100`

### Overall Score Calculation

Weighted average across all categories with findings:

```
overall = sum(category_percentage * category_weight) / sum(active_category_weights)
```

Categories with `max_score == 0` (no applicable checks) are excluded from both numerator and denominator.

## Adding a New Scanner

1. Create a new file in `backend/scanners/` following the existing pattern
2. Define `_CHECKS` list with `ScanCheck` instances
3. Implement `evaluate()` (or `evaluate_org()` for org-level)
4. Add the scanner to `ScanOrchestrator.__init__()` in the appropriate list
5. Ensure all category weights still sum to 1.0
6. Update benchmark mappings if the new checks align with any framework
7. Add tests in `tests/test_scanners/`
