---
slug: scan-results
title: Reading scan results
category: scans
order: 20
summary: How the scan detail page is laid out, how category scores are computed, what the severity bands mean, and how to read the evidence panel.
audience: [end-user]
last_reviewed: 2026-05-13
---

Once a scan completes, the scan detail page becomes the primary interface for understanding what BPS found. This page walks through every section of that view, explains how severity is graded, and shows how to filter the noise. The same information appears in the generated PDF, Excel, and Zip reports, but the scan detail page is interactive — filterable, drillable, and linkable.

## The scan detail page

The page is divided into four regions, top to bottom.

1. **Overall score banner** — weighted overall score from zero to one hundred, number of repositories scanned, number of findings, and the AI-generated executive summary.
2. **Per-category breakdown** — one row per scanner domain showing score, weight, and pass-fail counts.
3. **Findings table** — every individual check result, filterable by category, severity, and status.
4. **Benchmarks tab** — alternative view mapping findings to industry benchmarks (OpenSSF, DORA, SLSA, CIS).

## Per-category scores

Every finding contributes to its category's score. Each check has a weight, a status (passed, failed, manual review, or not applicable), and a numeric score from zero to one hundred. The category's percentage is `sum(score × weight) ÷ sum(weight) × 100`. The overall score is the weighted average of the 16 category scores, using these fixed weights.

| Category | Weight | Scope | Checks |
|---|---|---|---|
| Platform Architecture | 0.06 | org | 11 |
| Identity and Access Management | 0.10 | org | 12 |
| Repository Governance | 0.10 | repo | 12 |
| CI/CD Pipeline | 0.10 | repo | 14 |
| Secrets Management | 0.08 | repo | 10 |
| Dependency Management | 0.08 | repo | 11 |
| Static Application Security Testing | 0.06 | repo | 10 |
| Dynamic Application Security Testing | 0.04 | repo | 8 |
| Container Security | 0.06 | repo | 12 |
| Code Quality | 0.06 | repo | 9 |
| SDLC Process | 0.06 | repo | 12 |
| Compliance | 0.06 | repo | 11 |
| Collaboration | 0.04 | repo | 7 |
| Disaster Recovery | 0.04 | repo | 10 |
| Monitoring and Observability | 0.04 | repo | 11 |
| Migration Readiness | 0.02 | repo | 9 |

Weights sum to 1.0. A category with weight 0.10 and a score of 60 contributes six points; a category with weight 0.02 and a perfect score contributes only two. Identity and Access matters more than Migration Readiness in nearly every customer context.

> Tip: A scan profile can override category weights. When a profile disables a category, the remaining weights are renormalised so they still sum to 1.0.

## Severity bands

Each check carries a severity that classifies how serious a failure would be. Severities are fixed per check; they are not derived from the evidence.

| Severity | Meaning | Example check |
|---|---|---|
| critical | Failure represents an active security risk. Address immediately. | Missing branch protection on the default branch of a public repository. |
| high | Failure significantly weakens security or compliance posture. | No secret scanning enabled on a repository that contains production code. |
| medium | Failure suggests a recommended control is absent. | No CODEOWNERS file. |
| low | Failure is a quality or hygiene issue rather than a security one. | No CHANGELOG. |
| info | Informational only. Does not affect the score in most categories. | Repository created less than 30 days ago. |

The default findings table view shows failed findings of severity `medium` and above. Critical and high failures also appear in the executive summary. Toggle **Show all** to expose informational and passed findings — useful for confirming what BPS actually checked.

## Reading evidence

Clicking any row in the findings table opens an evidence drawer with:

- **Check name and ID** — for example `CICD-008: CI pipeline pass rate above threshold`.
- **Category and severity** — colour-coded badges.
- **Detail message** — a human-readable explanation produced by the scanner.
- **Evidence** — the structured JSON the scanner produced (file paths, config values, counts, percentages). The shape varies by check.
- **Remediation guidance** — for failed findings, a short paragraph explaining what to change. Where a built-in skill exists, this links into the skills library.

A typical evidence payload looks like this:

```json
{
  "check_id": "CICD-008",
  "category": "cicd",
  "severity": "medium",
  "status": "failed",
  "detail": "Pass rate of 78% across 50 recent runs is below the 95% threshold.",
  "evidence": {
    "total_runs": 50,
    "successful_runs": 39,
    "pass_rate": 0.78,
    "pass_threshold": 0.95,
    "warning_threshold": 0.80,
    "workflows_inspected": [".github/workflows/ci.yml"]
  }
}
```

> Note: Evidence is generated server-side from the scanner output and stored verbatim on the finding. It does not change once a scan completes — re-rendering the page always produces the same evidence for the same finding.

## Benchmarks tab

The Benchmarks tab maps findings onto four industry benchmarks.

- **OpenSSF Scorecard** — security posture score from zero to ten.
- **DORA metrics** — deployment frequency, lead time, change failure rate, mean time to recovery.
- **SLSA levels** — supply-chain maturity from level 1 to level 4.
- **CIS Software Supply Chain** — alignment with the CIS Software Supply Chain Security Benchmark v1.0.

Each benchmark card shows its overall score and the contributing findings. Clicking a contributing finding scrolls back to the findings table and opens the evidence drawer.

> Note: Benchmark scores are computed deterministically from findings, not by the AI analyser. Findings filtered out by a scan profile are excluded from the benchmark.

## Filtering

The findings table has three filter controls.

| Filter | Effect |
|---|---|
| Category | Show only findings from one of the 16 domains. |
| Severity | Show only findings at or above a chosen severity (info, low, medium, high, critical). |
| Status | Show only passed, failed, `manual_review`, or `not_applicable` findings. |

Filters compose: setting category to `cicd`, severity to `medium`, and status to `failed` gives you the actionable CI/CD findings only. The URL updates as you filter, so a filtered view is shareable.

> Tip: When triaging a large scan, start with severity `high` and status `failed`. This produces a short, action-oriented list that maps to the executive summary.

## See also

- [Glossary and concepts](/help/glossary) — what *Finding*, *Category Score*, and *Severity* mean.
- [Running your first scan](/help/first-scan) — how to produce the data this page renders.
- [Connecting GitHub, GitLab, and Azure DevOps](/help/platform-connections) — what BPS can and cannot see per platform.
- [Adding a customer](/help/customer-onboarding) — the parent record that owns a scan.
