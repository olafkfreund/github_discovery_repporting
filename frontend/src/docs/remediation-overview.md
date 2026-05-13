---
slug: remediation-overview
title: Agentic remediation overview
category: remediation
order: 10
summary: BPS can turn unresolved scan findings into pull requests by running an agent that applies per-check recipes, the customer's AGENTS.md profile and the active skills.
audience: [admin]
last_reviewed: 2026-05-13
---

Once a scan completes you have a list of findings. Reading them is the easy part — actually fixing them is the work. BPS includes an agentic remediation system that turns each remaining finding into an auditable pull request, governed by a per-customer policy and an organisation-wide kill switch.

> Note: Remediation is opt-in. A brand-new customer has `RemediationPolicy.enabled = false`. Nothing dispatches until an admin explicitly turns it on.

## What agentic remediation does

When you trigger an agent run against a completed scan, the agent walks the finding list, picks the next remediable one and assembles a tailored prompt from four ingredients:

1. The **per-check recipe** — a small, deterministic block of guidance specific to that check ID (for example, the recipe for CICD-001 explains what a workflow file should look like).
2. The customer's **AGENTS.md profile** — one of the four built-in profiles (Standard, Banking, Public Sector or Strict) or a customised version of one. See [AGENTS.md profiles](/help/agent-profiles).
3. The **active skills** for the customer's connection — small reusable instructions resolved through the skill resolver. See the [Skills system](/help/skills) article.
4. The **finding evidence** itself — the exact data the scanner captured.

The agent then opens a workspace, runs an LLM tool-use loop with a narrow tool registry, and produces a pull request against the repository. The PR references the finding ID in its body, attempts the smallest possible diff and is opened as a draft when the change touches CI workflows or security-sensitive configuration.

## Two runtime modes

`RemediationPolicy.runtime_mode` decides where the agent actually executes.

### Backend mode

In backend mode the agent runs inside the BPS backend process. The runner clones the repository to a sandboxed workspace, drives the LLM directly using the customer's `LLMConnection`, and opens the pull request via the platform API using the customer's stored PAT.

Best for tenants that trust BPS to act with their PAT and want the simplest deployment story. The full audit trail — every prompt, every tool call, every diff — is captured in the `agent_steps` table.

### CI mode

In CI mode the backend instead dispatches a workflow on the customer's own CI (GitHub Actions, GitLab CI or Azure Pipelines) using a workflow template the customer hosts. The customer's CI agent fetches the operator prompt over an HMAC-signed callback (the `callback_secret` is a 32-byte secret persisted on the `AgentRun` row) and posts progress events back to BPS via webhook.

Best for air-gapped or strict-control tenants who must keep the LLM-using process inside their own perimeter. BPS retains the audit trail; the customer retains custody of the LLM credentials and the code.

> Note: CI mode is delivered by issue #50 and may still be in flight. The `runtime_mode` column exists today; the dispatch path is conditional on the CI workflow template repo (`ci_workflow_repo`) being configured on the policy.

## Lifecycle states

An `AgentRun` row moves through these states. The terminal states are `completed`, `failed` and `cancelled`.

| State | Meaning |
| :--- | :--- |
| `pending` | Row created, kill-switch + cost-cap checks passed, awaiting dispatch |
| `running` | Loop is executing — LLM calls, tool calls, diffs being computed |
| `opening_pr` | All diffs decided, the platform API is being called to open PRs |
| `completed` | Terminal — at least one PR was opened (or zero if there was nothing to fix) |
| `failed` | Terminal — unrecoverable error; `error` column holds the message |
| `cancelled` | Terminal — operator cancelled or kill switch engaged mid-flight |

Each state transition writes an `AgentStep` row so the timeline can be rebuilt for audit. Rejection at run-creation time (kill switch engaged, cost cap exceeded, policy disabled) returns HTTP 409 from the API and never reaches the `pending` state — there is no row to inspect.

## Safety net

A handful of guardrails sit between the agent and your repository:

- **Three-layer kill switch** — Global (Settings → Stop all agent runs), customer-policy (`kill_switch_enabled`), or none. The first engaged layer wins and reports the layer plus a reason string. See [Remediation policy and cost caps](/help/remediation-policy).
- **Monthly USD cost cap per customer** — Defaults to `$100.00` in `RemediationPolicy.max_cost_usd_per_month`. New runs are rejected with HTTP 409 once the calendar-month spend equals or exceeds the cap.
- **Allowed and blocked path globs** — `allowed_path_globs` constrains the agent to specific directories; `denied_path_globs` overrides allow and is checked first. Empty allow-list means "all paths" (subject to deny).
- **Diff-scope guardrail** — REQ-061. Every diff is checked against the scope of the assigned finding before the PR is opened. Cross-scope writes are refused.
- **Tool allow-list** — REQ-060. The agent loop is wired to a narrow tool registry. Tools outside the registry cannot be invoked even if the LLM requests them.
- **Hash-chained audit log** — REQ-005. Every `AgentStep` is hash-chained, so an after-the-fact tampering attempt breaks the chain and is detectable.

The agent also probes the workspace for an existing AGENTS.md (or CLAUDE.md, `.cursorrules`, or `.github/copilot-instructions.md`) before injecting the customer's profile. If the repository already has its own instructions, those are used and the BPS profile is not prepended.

## When to enable

A recommended progression for a new customer:

1. **Dry-run on a sandbox repo** — keep `enabled = true` but pick a single low-risk repository. Trigger one run manually and inspect every PR before merging.
2. **Manual trigger on non-prod repos** — leave `auto_dispatch = false`. Operators trigger runs from the scan results page after reviewing the finding list.
3. **Auto-dispatch** — only flip `auto_dispatch = true` once you have observed several manual runs behaving exactly as expected, and after you have tightened `denied_path_globs` to exclude anything genuinely sensitive.

The cost cap acts as a circuit breaker throughout. Start at the default `$100/month` per customer and raise it deliberately as confidence grows.

```json
{
  "enabled": true,
  "auto_dispatch": false,
  "runtime_mode": "backend",
  "max_cost_usd_per_month": 100.0,
  "max_prs_per_scan": 5,
  "allowed_path_globs": ["apps/**", "services/**"],
  "denied_path_globs": ["secrets/**", "infra/prod/**", "**/CHANGELOG.md"]
}
```

## Next steps

- [Remediation policy and cost caps](/help/remediation-policy) — every policy field explained.
- [Configuring LLM providers](/help/llm-providers) — which providers and models the agent can use.
- [AGENTS.md profiles](/help/agent-profiles) — the four built-in profiles and how to customise them.
- [Skills system](/help/skills) — how skills attach extra guidance to specific connections.
