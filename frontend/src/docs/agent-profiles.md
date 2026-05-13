---
slug: agent-profiles
title: AGENTS.md profiles
category: skills-profiles
order: 10
summary: BPS ships four built-in AGENTS.md profiles — Standard, Banking/Fintech, Public Sector and Strict — that shape how the remediation agent behaves and what it refuses to do.
audience: [admin]
last_reviewed: 2026-05-13
---

An AGENTS.md is a document that sits at the root of a repository and shapes how AI coding agents behave inside it: what they are authorised to do, what they must refuse, the conventions they should follow, and how they should escalate when uncertain. BPS ships four ready-made profiles and uses them as the starting point for the per-customer instruction text that drives the remediation agent.

> Note: When the BPS agent opens a workspace it first probes for an existing `AGENTS.md` (or `CLAUDE.md`, `.cursorrules` or `.github/copilot-instructions.md`). If any are present, the repository's own instructions are used and the customer's BPS profile is not injected.

## What is AGENTS.md?

`AGENTS.md` is a community convention — a markdown document, in the repository root, that an AI coding agent reads before it acts. It is the equivalent of `CONTRIBUTING.md` for humans: a single, version-controlled place to record what the agent should and should not do.

BPS stores the customer-level AGENTS.md text in `AgentInstructions.content`. When the remediation agent runs and the target repository has no AGENTS.md of its own, BPS prepends the customer's content to the system prompt. The `profile_slug` column on the same row records which built-in profile the text was originally seeded from, even if the operator has since edited the body.

## The four profiles

| Profile | Posture | Auto-merge | Audit detail | Typical sector |
| :--- | :--- | :--- | :--- | :--- |
| Standard | Pragmatic — assist, but keep humans in the loop | Allowed by policy (`oversight_mode = "standard"`) | Standard step-by-step trace | SaaS, startups, internal tooling teams |
| Banking / Fintech | Stricter — change-control aware, draft PRs only | Never | Heavy — every action logged with regulatory framing | Financial services under FCA / PCI / SOX |
| Public Sector | Conservative, plain English, WCAG 2.2 AA, air-gappable | Never | Plain-English audit, FOI-aware language | Government, education, healthcare |
| Strict | Refuses by default — per-finding human approval | Never | Maximum — explicit approval ledger | Highly regulated, opt-in trials, post-incident |

All four profiles share the same section structure (see "What each profile covers" below) but differ in the authority they grant, the language they use and what they refuse to do.

### Standard

Sensible defaults for most software teams. The agent is authorised to open pull requests for auto-remediable findings and suggest changes via PR comment for findings that need judgement. It is not authorised to merge, push to the default branch, modify secrets or act outside the assigned findings. Human review is required on every PR.

### Banking / Fintech

For organisations subject to formal change-control regimes. All PRs are opened as drafts with a `change-control-pending` label. Direct pushes to `main`, `master`, `prod`, `release` and `hotfix/*` are forbidden. Deployment-controlling workflow files cannot be edited without per-finding operator approval. The narrative cites REQ-001 (scope limited to assigned findings) explicitly.

### Public Sector

For air-gapped or restricted-network environments. The agent assumes no outbound connectivity is available, will not call package registries or telemetry endpoints, and uses plain English in PR bodies and comments. WCAG 2.2 AA accessibility considerations are noted in PR descriptions when the change touches user-facing surfaces. REQ-091 (air-gapped operation) applies.

### Strict

The defensive posture. The agent refuses every action by default; each finding requires a separate explicit approval from an operator before the agent may produce even a draft proposal. No chained approvals — approving finding A never implies approval for finding B. This profile is the right starting point for the first time you enable remediation, post-incident recovery periods, or any context where the cost of an over-eager change is high.

## Picking a profile

The profile picker lives at `/settings/agent-instructions?customer_id=<id>`. The first time you visit it for a new customer you see four cards (one per profile) plus a "Start blank" option. Clicking a card loads the profile's full markdown body into the textarea and records the `profile_slug` on save. Subsequent saves overwrite the body but leave the slug intact so the audit trail remembers what was used as the starting point.

The flow is intentionally explicit. There is no automatic profile detection. The choice is recorded against the human-readable slug — `standard`, `banking`, `public-sector` or `strict` — and the body hash (SHA-256 of the loaded markdown) is captured for audit per REQ-052 (prompt-versioning).

## Customising after picking

The textarea is freely editable. Save persists the body verbatim — every line, including any edits you made — to `AgentInstructions.content`. The `profile_slug` is not affected by edits to the body; it only changes when you explicitly use the **Replace with profile…** button to re-seed from a different starting point. The confirm dialog warns that re-seeding overwrites the textarea contents.

This separation matters for auditors. A reviewer can ask: "what was this customer's starting point?" — answered by the slug. And: "what exactly did the agent see?" — answered by the body and its SHA-256.

```json
{
  "customer_id": "9d2e1b40-7d4e-4cf1-9b2c-2f08c4a7ab93",
  "profile_slug": "banking",
  "content": "# Agent Instructions — Banking / Fintech\n\n## Purpose...\n\n(...customer's edited body...)",
  "content_sha256": "e3a1f7c0d9...c4",
  "is_active": true
}
```

## What each profile covers

Every shipped profile follows the same section taxonomy so reviewers always know where to look:

- **Purpose** — the regulatory or organisational context the profile is designed for.
- **Authority and scope** — the explicit allow-list and deny-list of actions.
- **Code review and PR conventions** — PR title format, branch naming, label requirements, draft-or-not rules.
- **Security and secrets** — handling of credentials, environment variables, secrets-management files.
- **Build, test and verify** — what the agent must run before opening a PR.
- **Code style** — language and convention pointers.
- **Compliance** — mapped REQ-* identifiers and standards (PCI, SOX, WCAG, FOI).
- **Skills and recipes** — how built-in skills compose on top of the profile.
- **Escalation and refusal** — what to do when the agent cannot proceed within authority.
- **Audit and logging** — what is recorded and how detailed.

Reading any of the four shipped profiles end to end is a 10-minute exercise. We recommend doing exactly that before committing to one for a customer.

## Browse the profiles

The live gallery at [/help/profiles](/help/profiles) renders the four profiles from the API, including their full markdown bodies and SHA-256 hashes. Use it to compare side by side before choosing, or after the fact to confirm what was active during a specific historical scan.

## Next steps

- [Skills system](/help/skills) — how skills layer on top of the chosen profile.
- [Agentic remediation overview](/help/remediation-overview) — where the profile fits in the runtime.
- [Remediation policy and cost caps](/help/remediation-policy) — the policy that complements the profile.
