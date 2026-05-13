---
slug: scan-profiles
title: Customising scan profiles
category: scans
order: 30
summary: Scan profiles let admins disable irrelevant categories, mute specific checks, override category weights and tune per-check thresholds for a customer's risk appetite.
audience: [admin]
last_reviewed: 2026-05-13
---

A standard scan in BPS runs every one of the 16 scanner domains with the default weights — appropriate for a first pass but rarely the right shape for a long-lived customer engagement. Scan profiles let you record a customer-specific scanner configuration once and reuse it on every scan.

## Why profiles?

Out of the box, BPS runs all 16 categories at their default weights, applies the hardcoded threshold for every check, and reports against every control. That works for a baseline assessment but produces noise once you know a customer's context. For example:

- A SaaS team that does not ship containers does not need the Container Security category to drag their overall score down.
- A regulated financial services customer cares more about the SAST and Compliance categories than the default weights reflect.
- A small team that runs trunk-based development with one reviewer should not be penalised by the default `min_review_count` of two.

A scan profile captures these adjustments. Once defined, the profile can be selected from the scan trigger form on the customer detail page and is then snapshotted into the scan record for reproducibility.

## Anatomy of a profile

A profile is a row in `scan_profiles` with three pieces of metadata (`name`, `description`, `is_default`) plus a sparse JSON `config` blob. Sparse means that any category, check or threshold not mentioned in `config` falls back to its scanner-defined default.

The JSON shape is:

```json
{
  "name": "Fintech baseline",
  "description": "No Docker, SAST-weighted, stricter coverage",
  "is_default": false,
  "config": {
    "categories": {
      "<category_key>": {
        "enabled": true,
        "weight": 0.12,
        "checks": {
          "<CHECK-ID>": {
            "enabled": false,
            "thresholds": { "min_coverage_pct": 85.0 }
          }
        }
      }
    }
  }
}
```

The orchestrator filters out any category or check where `enabled: false`, applies the optional `weight` override on each remaining category, then re-normalises so the enabled categories sum to 1.0 again. Per-check `thresholds` are merged with the hardcoded defaults — only keys you supply override.

## Editing in the UI

Profiles are managed at `/customers/:id/scan-profiles`. The page lists existing profiles for the customer along with a **New profile** button.

The editor renders one collapsible accordion per category. By default every category is collapsed; expanding one reveals a per-check list with a toggle and, where relevant, a small input for each threshold key the check exposes. A summary at the bottom shows the live total weight across enabled categories — if it drifts from 1.0 the editor displays a yellow warning, but you can still save (the orchestrator will renormalise at scan time).

The category-level controls are:

- An **Enable / Disable** toggle.
- A **Weight** input (decimal between 0 and 1).
- A search-filterable list of checks for that category.

## Threshold-tunable checks

Seven checks accept per-customer threshold overrides. These are the keys and the hardcoded defaults that ship with BPS:

| Check ID | Threshold key | Default | What it controls |
| :--- | :--- | ---: | :--- |
| CICD-008 | `pass_threshold` | 0.95 | Fraction of workflows that must be passing for the check to pass |
| CICD-008 | `warning_threshold` | 0.80 | Fraction below which the check flips to warning |
| CICD-009 | `max_seconds` | 600 | Maximum acceptable CI run duration in seconds |
| IAM-003 | `max_admin_ratio` | 0.05 | Maximum acceptable ratio of admin members to total members |
| CQ-004 | `min_coverage_pct` | 60.0 | Minimum acceptable test coverage percentage |
| SDLC-003 | `pass_threshold` | 0.75 | Pass fraction for review-coverage checks |
| SDLC-003 | `warning_threshold` | 0.50 | Warning fraction for review-coverage checks |
| SDLC-004 | `pass_threshold` | 500 | Maximum acceptable lines changed per PR for pass |
| SDLC-004 | `warning_threshold` | 1000 | Maximum acceptable lines per PR before warning |
| COLLAB-006 | `pass_threshold` | 0.90 | Pass fraction for reviewer coverage on PRs |
| COLLAB-006 | `warning_threshold` | 0.75 | Warning fraction for reviewer coverage |

The full registry (including which thresholds exist on which check) is available from `GET /api/scanners/registry`. The frontend profile editor reads that endpoint at load time so newly added thresholds appear automatically.

> Tip: Raise pass thresholds gradually. Jumping from the 0.75 default for SDLC-003 to 0.95 in one step usually produces a flood of warnings on the next scan; bump to 0.85 first and let the team converge.

## Worked example

A fintech customer with the following characteristics:

- Ships exclusively to managed cloud runtimes; no Dockerfiles in the estate.
- Migration Readiness is not relevant — they are not planning a platform move.
- Security posture is paramount, so they want SAST to weigh twice as much as the default.
- Compliance team mandates 85 percent test coverage.

The resulting profile is below. Note how it is sparse — categories not mentioned in `config` use defaults.

```json
{
  "name": "Fintech baseline",
  "description": "No Docker, no migration, SAST-weighted, 85% coverage",
  "is_default": true,
  "config": {
    "categories": {
      "container_security": { "enabled": false },
      "migration": { "enabled": false },
      "sast": { "weight": 0.12 },
      "code_quality": {
        "checks": {
          "CQ-004": {
            "thresholds": { "min_coverage_pct": 85.0 }
          }
        }
      }
    }
  }
}
```

The orchestrator will skip Container Security and Migration Readiness entirely (those findings never appear in the report), apply weight 0.12 to SAST instead of the default 0.06, then renormalise the remaining 14 enabled categories so they sum to 1.0.

## Profile reproducibility

When a scan starts, the chosen profile's `config` is serialised into `Scan.scan_config`. Editing the profile later — adding a check, raising a threshold, disabling a category — does not change historical scans. Re-running last quarter's scan with last quarter's profile snapshot will produce exactly the same scoring, even if the active profile has since changed.

This is the audit-safe default. If you want a scan to use the latest profile configuration, trigger a new scan; the orchestrator will read the live profile at the moment of trigger.

> Note: The snapshot only captures the profile config. Scanner code changes between BPS releases will still affect re-scanned data. The audit trail records both the profile snapshot and the BPS version so reviewers can correlate.

## Next steps

- [Reading scan results](/help/scan-results) — see how profile changes affect the score breakdown.
- [Generating and downloading reports](/help/reports) — reports inherit the profile that drove the scan.
- [Compliance & audit](/help/compliance) — how profile snapshots feed the audit log.
