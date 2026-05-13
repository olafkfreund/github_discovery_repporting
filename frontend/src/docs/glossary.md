---
slug: glossary
title: Glossary and concepts
category: getting-started
order: 20
summary: A single-page reference for every BPS term used throughout the documentation, from Customers and Scans to REQ-* compliance identifiers.
audience: [end-user, admin]
last_reviewed: 2026-05-13
---

BPS introduces a number of domain-specific terms that recur throughout the rest of the documentation. This page is the canonical reference for what each one means. Skim it once before reading the other articles, then use it as a lookup when something is unfamiliar.

The glossary is organised into four groups: core data objects, the agentic remediation system, safety and governance, and compliance identifiers. Cross-links point at the article where each term is described in more depth.

## Core data objects

These are the primary records you create and interact with through the portal.

### Customer

A tenant entity in BPS. Each customer owns its own [platform connections](/help/platform-connections), [scan profiles](/help/first-scan), AGENTS.md instructions, [remediation policy](/help/first-scan), [LLM connections](/help/first-scan), [skills](/help/glossary#skill), and audit history. Customers are normally one per client organisation or business unit. A customer has a stable UUID, a display name, an optional contact email, and free-form notes. See [Adding a customer](/help/customer-onboarding).

### Platform Connection

The encrypted credentials BPS uses to talk to one GitHub organisation, one GitLab group, or one Azure DevOps organisation. A customer can have many connections, and each one is scanned independently. Credentials are encrypted at rest using Fernet symmetric encryption with the `CREDENTIALS_ENCRYPTION_KEY` environment variable. See [Connecting GitHub, GitLab, and Azure DevOps](/help/platform-connections).

### Scan

A point-in-time assessment of one platform connection. A scan runs in two phases: organisation-level checks (membership, security policy, default permissions) and per-repository checks (branch protection, CI workflows, secrets configuration, and so on). Scans transition through the states `pending`, `scanning`, and either `completed` or `failed`. The portal displays these as queued, running, completed, and failed respectively. See [Running your first scan](/help/first-scan).

### Finding

A single check result inside a scan. Every finding records the `check_id` (for example `CICD-008`), a severity, a status (`passed`, `failed`, `manual_review`, or `not_applicable`), a human-readable detail message, and structured evidence (JSON data showing what BPS actually saw). Findings are grouped by category in the [results UI](/help/scan-results).

### Category Score

A weighted score from zero to one hundred for one of the 16 scanner domains (for example CI/CD Pipeline or Secrets Management). Each finding earns or loses points within its category, and the overall scan score is the weighted average of the 16 category scores. See [Reading scan results](/help/scan-results).

### Report

A generated artefact summarising a completed scan. BPS produces three formats: a board-ready PDF, a multi-sheet Excel workbook, and a Zip bundle containing the Excel file alongside structured Markdown files suitable for version control. Reports are stored on the server and downloadable from the scan results page.

### Scan Profile

A per-customer configuration document that customises a scan. A profile can disable entire categories, toggle individual checks on or off, override category weights, and tune per-check thresholds such as `CICD-008.pass_threshold`. When a scan is triggered, the profile config is snapshotted into the scan record so the run is reproducible even if the profile changes later.

## Agentic remediation

These terms describe how BPS turns failing findings into automated pull requests.

### Agent Run

One execution of the remediation agent against a chosen set of failing findings. An agent run has a lifecycle (`pending`, `running`, `completed`, `failed`, `cancelled`), a cost record, a hash-chained audit log, and zero or more pull requests opened on the target platform. Agent runs operate in one of two runtime modes.

### Runtime mode

Either `backend` or `ci`. In `backend` mode the agent executes inside the BPS server itself, calling provider write APIs directly. In `ci` mode BPS dispatches the agent via a GitHub Actions workflow (or platform equivalent), so all writes originate from inside the customer's CI environment. The choice affects egress requirements and the trust boundary; see [Running your first scan](/help/first-scan) for a brief overview.

### Skill

A short Markdown document with YAML frontmatter that shapes how the agent thinks about a particular check or category. BPS ships with 15 built-in skills covering common remediation patterns (for example "add a CODEOWNERS file" or "enable branch protection"). Customers may also author custom skills and override the built-in ones on a per-connection basis using a tri-state toggle (force on, force off, or inherit).

### AGENTS.md profile

One of four curated starting templates for a customer's agent instructions: **Standard**, **Banking / Fintech**, **Public Sector**, and **Strict**. Each profile sets opinionated defaults for tone, tool restrictions, escalation behaviour, and audit verbosity. You can pick a profile when onboarding a customer and edit the resulting AGENTS.md content freely afterwards.

### Remediation Policy

Per-customer configuration that governs the safety net around agentic remediation: the kill switch, monthly cost cap in USD, optional per-run cost cap, allow-list and block-list for repository paths, and the `auto_dispatch` toggle that triggers an agent run automatically after every successful scan.

### LLM Connection

Encrypted credentials for one large-language-model provider. BPS supports six providers: Anthropic (direct API), OpenAI, Amazon Bedrock, Azure OpenAI, Google Vertex AI, and any OpenAI-compatible endpoint (for example a self-hosted vLLM server). A customer can have several LLM connections; one of them is marked as the default and used for new agent runs unless overridden.

## Safety and governance

These terms describe how BPS prevents the agent from doing something you did not authorise.

### Kill Switch

A three-layer safety net. When the global kill switch is engaged (system administrator scope), no agent runs may start anywhere in the deployment. When a customer's policy kill switch is engaged, no agent runs may start for that customer. When neither is engaged, runs proceed normally. The kill switch is intentionally additive — turning it on never destroys data, and turning it off restores normal behaviour.

```json
{
  "kill_switch_layers": {
    "global": false,
    "customer_policy": false,
    "engaged": false
  }
}
```

### Cost cap

A monthly USD budget that BPS enforces before every agent run. The aggregator sums all LLM costs from prior runs in the current calendar month and rejects any new run whose estimated cost would push the total over the cap. The optional per-run cost cap rejects runs whose estimate exceeds a single-run limit, which is useful for blocking accidentally large code-rewrite tasks.

### Allow-list and block-list

Lists of repository-path glob patterns that scope what the agent may touch. The allow-list, when non-empty, restricts writes to matching paths only. The block-list always wins over the allow-list, so a path matched by both is blocked. Common patterns: allow `**/*.yml` and `.github/**` for CI fixes only; block `**/secrets/**` and `**/*.env` everywhere.

## Compliance identifiers

BPS uses numbered `REQ-*` identifiers to make compliance traceability explicit. The full list is in [Compliance and audit](/help/compliance); this glossary lists the eight most-referenced ones.

| ID | Topic | Summary |
|---|---|---|
| REQ-001 | PR disclosure | Every agent-opened PR includes a standard disclosure block identifying BPS as the author. |
| REQ-005 | Hash-chained audit | Each audit log entry includes the SHA-256 hash of the previous entry, so tampering is detectable. |
| REQ-030 | PII redaction | Personally identifiable data is stripped before findings are sent to any LLM. |
| REQ-031 | Hunk-only LLM input | Only the diff hunks under review are sent to the LLM, never the full repository. |
| REQ-052 | Versioned prompts | All system prompts are versioned and the version used is recorded on every run. |
| REQ-060 | Tool allow-list | Agents may invoke only an explicit, per-profile list of tools. |
| REQ-061 | Diff-scope guardrail | Final commits are rejected when they touch files outside the original finding's scope. |
| REQ-091 | Air-gapped | The deployment can run without any outbound internet beyond your configured LLM endpoint. |

> Note: The REQ-* numbering is internal to BPS and does not map one-to-one with any external standard. Mappings to OpenSSF, DORA, SLSA, and CIS are produced separately on the Benchmarks tab of every scan.

## See also

- [Getting Started with BPS](/help/getting-started) — five-minute overview of the whole product.
- [Adding a customer](/help/customer-onboarding) — your first step when onboarding a new tenant.
- [Connecting GitHub, GitLab, and Azure DevOps](/help/platform-connections) — required token scopes per provider.
- [Running your first scan](/help/first-scan) — what each phase does and how to interpret status changes.
- [Reading scan results](/help/scan-results) — category scores, severity bands, evidence panel, and benchmarks.
