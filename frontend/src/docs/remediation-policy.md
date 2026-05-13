---
slug: remediation-policy
title: Remediation policy and cost caps
category: remediation
order: 30
summary: The per-customer remediation policy governs the agent — the master toggle, the auto-dispatch flag, the monthly USD cost cap, the path globs and the three-layer kill switch.
audience: [admin]
last_reviewed: 2026-05-13
---

The `RemediationPolicy` row is the single record that controls everything the BPS agent is allowed to do on behalf of a customer. Exactly one row per customer, enforced by a unique constraint on `customer_id`, with safe-by-default values so a freshly added customer cannot accidentally dispatch a run.

> Note: A customer with no policy row is treated as fully disabled. Triggering a run against such a customer returns HTTP 409.

## What the policy controls

| Field | Default | Purpose |
| :--- | :--- | :--- |
| `enabled` | `false` | Master toggle. When `false`, no run is permitted regardless of any other field. |
| `kill_switch_enabled` | `false` | Customer-layer emergency stop. Wins over `auto_dispatch`. |
| `auto_dispatch` | `false` | When `true`, the scan-completion event automatically creates and triggers an agent run for failing findings. When `false`, runs are manual. |
| `max_cost_usd_per_month` | `100.0` | Hard ceiling on cumulative `AgentRun.total_cost_usd` since the first day of the current calendar month (UTC). |
| `max_prs_per_scan` | `10` | Upper bound on pull requests opened in a single run. |
| `allowed_check_ids` | `[]` | Allowlist of check IDs the agent may act on. Empty means "all checks". |
| `blocked_check_ids` | `[]` | Denylist of check IDs. Wins over `allowed_check_ids`. |
| `allowed_path_globs` | `[]` | Glob patterns restricting writes. Empty means "all paths". |
| `denied_path_globs` | `[]` | Glob patterns the agent must never touch. Wins over `allowed_path_globs`. |
| `runtime_mode` | `"backend"` | `"backend"` (agent runs in BPS) or `"ci"` (agent runs on customer CI). |
| `oversight_mode` | `"strict"` | `"strict"` (PR review required before merge) or `"standard"` (low-risk auto-merge allowed). |
| `llm_input_scope` | `"hunk"` | How much code context the LLM sees per call: `"hunk"`, `"file"` or `"repo-context"`. |
| `ci_workflow_repo` | `null` | Repo URL hosting the workflow template (CI runtime mode). |
| `ci_workflow_ref` | `null` | Git ref of the workflow template (CI runtime mode). |

Defaults are intentionally conservative. Turning on remediation is a deliberate, multi-toggle action.

## Three-layer kill switch

`kill_switch_service.check(db, customer_id)` returns a `KillSwitchState` with three possible `layer` values. Checks run in priority order and short-circuit on the first engaged layer.

### Layer 1: Global

Set on the singleton `Setting` row via **Global Settings → Stop all agent runs**. When engaged, every customer is blocked. The check returns `layer="global"` with the reason `"Global kill switch is engaged."`. Use this when you need to halt all automation across the platform, for example during an incident.

### Layer 2: Customer policy

Set on the customer's `RemediationPolicy.kill_switch_enabled`. When engaged, only that customer is blocked. The check returns `layer="customer"` with a reason that includes the customer UUID. Use this to ring-fence a single tenant — for example, after observing unexpected agent behaviour.

### Layer 3: None

Both upper layers are off. The check returns `layer="none"` with `reason=None` and remediation proceeds normally.

The lifecycle effect is the same in all engaged layers: `agent_service.create_agent_run` rejects the new run before any state is persisted. There is no `AgentRun` row to inspect because the rejection happens at creation time.

> Tip: Use the customer-layer switch for surgical halts. The global switch is the right tool for incident response or a release-window freeze, not for routine per-customer adjustment.

## Path globs in practice

Path globs determine which files the agent is allowed to modify. `denied_path_globs` is evaluated first and wins on conflict, exactly like `.gitignore` semantics. A worked example for a fintech customer who wants to keep secrets and production infrastructure beyond reach of any automation:

```json
{
  "allowed_path_globs": ["apps/**", "services/**", "tests/**"],
  "denied_path_globs": [
    "secrets/**",
    "infra/prod/**",
    "**/CHANGELOG.md",
    "**/.terraform/**",
    "**/*.tfstate"
  ]
}
```

With this configuration:

- A patch to `apps/web/src/auth.ts` is allowed.
- A patch to `infra/prod/main.tf` is denied even though it sits outside the explicit allow-list (because deny wins).
- A patch to `infra/staging/main.tf` is denied because nothing in the allow-list matches.
- A patch to `CHANGELOG.md` at any depth is denied.

Empty `allowed_path_globs` means "everything allowed" — fine for a small experiment but rarely the right production setting. We recommend an explicit allow-list once you have a feel for which directories the agent should be touching.

## Cost cap formula

The cap is checked on every new run. The formula is:

```
spent_usd      = SUM(AgentRun.total_cost_usd
                     WHERE Scan.customer_id == customer_id
                       AND AgentRun.created_at >= start_of_current_month_utc)

remaining_usd  = max(0.0, cap_usd - spent_usd)

exceeded       = spent_usd >= cap_usd
```

When `exceeded` is `true`, `agent_service.create_agent_run` returns HTTP 409 with a message naming the cap and the current spend. The check is read-only — it makes no writes and never affects existing in-flight runs. Caps reset implicitly when the calendar month rolls over in UTC.

The cap covers only agent costs. The cheaper AI summary path on scan reports is metered (you can read it from `Scan.summary_cost_usd`) but is not gated.

> Note: The cap is per customer, not per LLM connection. If a customer has two connections (Opus for remediation, Sonnet for summaries), both feed into the same monthly total when used by the agent.

## Updating policy

The policy editor lives at `/settings/remediation-policy?customer_id=<id>`. It uses the standard BPS save/discard pattern: edits enable a green **Save changes** button and a grey **Discard** button; after a successful save a "Saved 2 seconds ago" indicator appears in the page header and fades.

Field changes take effect on the next `agent_service.create_agent_run` call — they do not interrupt in-flight runs. If you need to halt running work, engage the customer-layer kill switch instead.

```json
{
  "enabled": true,
  "auto_dispatch": false,
  "kill_switch_enabled": false,
  "runtime_mode": "backend",
  "oversight_mode": "strict",
  "max_prs_per_scan": 5,
  "max_cost_usd_per_month": 250.0,
  "allowed_path_globs": ["apps/**", "services/**"],
  "denied_path_globs": ["secrets/**", "infra/prod/**", "**/CHANGELOG.md"],
  "blocked_check_ids": ["MIG-001", "MIG-002"]
}
```

## Next steps

- [Agentic remediation overview](/help/remediation-overview) — the lifecycle and runtime modes.
- [Configuring LLM providers](/help/llm-providers) — which models contribute to the monthly cap.
- [AGENTS.md profiles](/help/agent-profiles) — the behavioural posture the agent inherits.
- [Global settings](/help/global-settings) — the layer-1 kill switch and the global default LLM connection.
