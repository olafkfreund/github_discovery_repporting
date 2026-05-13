---
slug: compliance
title: Compliance & audit
category: admin
order: 10
summary: The REQ-* framework, the hash-chained audit log, kill-switch state history, data-residency hints, and retention policy in BPS.
audience: [admin]
last_reviewed: 2026-05-13
---

# Compliance & audit

BPS is designed for use in regulated environments where every agent action must be attributable, every prompt must be reproducible, and every change to a guardrail must be discoverable after the fact. This page summarises the controls that compliance teams rely on most often.

## The REQ-* framework

The shipped AGENTS.md profiles cite a set of internal requirement identifiers (`REQ-001`, `REQ-005`, and similar). They are pinned in every profile body so that downstream consumers — agent operators, auditors, and the agent itself — can name and reason about them precisely. The current set is:

| ID | Topic | Where implemented |
|---|---|---|
| REQ-001 | Agent actions scoped to assigned findings | Enforced by the agent runtime's tool allow-list and diff-scope guardrail |
| REQ-003 | Every PR references a traceable finding ID | PR body template includes the finding ID and the agent run ID |
| REQ-005 | No credential exfiltration | Tool allow-list + secrets redaction on every tool-call payload |
| REQ-030 | No direct push to default or protected branches | All changes land via PR; the agent has no push-to-default permission |
| REQ-031 | LLM input limited to relevant hunks | The runtime sends only the changed hunks, not full files, into the prompt |
| REQ-052 | All LLM calls use versioned prompt templates | Per-check operator templates carry an explicit version + SHA, recorded per step |
| REQ-060 | Secrets findings escalated, not auto-remediated | The Strict and Banking profiles refuse the SEC-* domain entirely; the agent opens an issue instead |
| REQ-061 | Sensitive file paths excluded from LLM context | A path deny-list filters the hunks before they reach the model |
| REQ-091 | Operations function without outbound internet | Public-sector profile + a customer LLM connection on the approved on-premises list |

> The exact wording of each REQ-* citation is preserved verbatim in the shipped profiles under `backend/agent_profiles/`. Refer to those files when writing assurance documentation.

## The hash-chained audit log

Every agent run is decomposed into ordered `AgentStep` rows. For each step the runtime persists:

- `tool_name` — the bounded tool that was invoked (`read_file`, `apply_patch`, `open_pr`, and so on).
- `tool_args` — the arguments, with secrets redacted before write.
- `tool_result` — the result, also redacted.
- `prompt_hash` — a SHA-256 deterministic from the inputs to that LLM call.
- `cost_usd` — the per-step cost contribution, in USD.

The `prompt_hash` for any step is computed from the SHA of the per-check operator template plus the concatenated SHAs of every skill body that was active, in selection order. An auditor who has the registry snapshot from the time the run executed can recompute the hash and compare; a mismatch means the prompt was tampered with or the registry has drifted.

The Agent run detail page exposes each step row in chronological order, including its tool, redacted arguments, and the prompt hash. Compliance reviewers commonly start from a remediation PR, follow the agent-run link in the disclosure block, and walk the step list to verify that the agent only edited paths in the finding's blast radius.

## Kill-switch state history

The kill switch has three layers and short-circuits as soon as the first engaged layer is found:

1. **Global** — controlled via `GET/PUT /api/settings` (the `global_kill_switch_enabled` boolean). When engaged, no agent run can start for any customer.
2. **Customer** — controlled via the `RemediationPolicy` row's `kill_switch_enabled` field.
3. **None** — the run is allowed to proceed (subject to the cost cap, profile, and PR cap).

Both the singleton settings row and every `RemediationPolicy` row carry standard `created_at` and `updated_at` timestamps, so the time at which each layer last changed state is recoverable. The Global Settings page in the UI reflects the engaged state visibly so an operator can confirm at a glance that the switch is held in the intended position.

## Data-residency hint

Global Settings exposes a `default_data_residency_region` value — a short ISO-style region tag (default `eu-west`). It does not pin LLM routing on its own; it is published so that compliance teams can align their LLM connection picks with a documented residency policy. The hint travels in every agent run record as an attribute on the customer's effective LLM connection.

## Retention

Global Settings holds two retention dials:

- `audit_log_retention_days` — how long audit-log entries are retained before scheduled pruning (default 180 days; range 30–3650).
- `streaming_log_retention_hours` — how long streaming-run logs are retained (default 72 hours; range 1–720).

Audit retention is set higher than streaming-log retention because the agent steps are the legal record; streaming logs are derivative and chiefly useful for live debugging. Report retention is managed independently by the report-cleanup task and defaults are documented on the [Global Settings](/help/global-settings) page.

## Reading the agent run detail page

The detail page at `/agents/:id` is the primary surface for compliance review:

- The header shows the run state, the customer, the scan, the runtime mode (backend or CI), and the chosen AGENTS.md profile.
- The cost panel shows the running USD total, the cap state at trigger time, and the projected end-of-month spend.
- The step list shows each invocation, the tool, the redacted arguments and result, and the prompt hash.
- The disclosure block at the bottom carries the human-readable finding citation and PR URL.

A complete audit story consists of: the customer policy at trigger time, the cost-cap state at trigger time, the resolved profile slug, the resolved skill set (by hash), and the ordered step list. All five are persisted on the agent run row or its child step rows.
