---
slug: skills
title: Skills system
category: skills-profiles
order: 20
summary: How skills augment per-check operator prompts with reusable prose context, where they apply, and how to author your own.
audience: [admin]
last_reviewed: 2026-05-13
---

# Skills system

A *skill* in BPS is a small markdown document — frontmatter plus body — that the agent system prepends to its own context when working on a matching check or category. Where the per-check operator template tells the agent **what** to do (a deterministic recipe), a skill tells the agent **how to think about it** (the prose-context layer). Skills are designed to be authored, reviewed, and version-controlled like any other piece of documentation, and the runtime hashes every skill body that influenced a prompt so the trail is auditable.

## What is a skill?

A skill is a single `.md` file with a YAML frontmatter header. The frontmatter declares which checks the skill applies to and which trigger contexts it participates in. The body is plain markdown — typically a few hundred words explaining the convention, citing the relevant authority (OpenSSF, CIS, DORA), and listing concrete dos and don'ts.

When the agent runs against a finding, the runtime walks the enabled skills, picks every one whose `applies_to` list includes the finding's `check_id` (or whose `applies_to` is empty — those are always-on), concatenates the bodies, and injects them into the system prompt above the per-check operator template. The same selection runs for the optional post-scan LLM enrichment pass.

```yaml
---
name: branch-protection-baseline
description: Defines the minimum branch-protection rules expected on default branches.
category: repo_governance
applies_to:
  - REPO-001
  - REPO-002
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - openssf-scorecard
---

# Branch protection baseline

The default branch must require pull-request review before merge…
```

## Built-in vs custom skills

BPS ships 15 built-in skills under `backend/skills/library/`. They cover the most common cross-platform conventions: branch protection baselines, CODEOWNERS team mapping, CodeQL workflow patterns, container-image rootless hardening, gitleaks config conventions, workflow pinning, dependency-update policy, and similar. Built-in skills are read-only — you cannot delete them or edit their body via the UI — but every customer can toggle each one on or off independently.

Custom skills are authored by the customer via the Settings → Skills page. They use the same schema as built-in skills and are validated against the live scanner registry at save time. If you reference an unknown `check_id` in `applies_to`, the save fails before any data is persisted.

| Trait | Built-in | Custom |
|---|---|---|
| Authored by | BPS team | Customer admin |
| Storage | Static markdown files | Database row |
| Editable body | No | Yes |
| Per-customer toggle | Yes | Yes |
| Per-connection override | Yes | Yes |

## Where skills apply

Each skill declares a `triggers` list. Two values are supported:

- `remediation` — the skill body is concatenated into the system prompt every time the agent works on a finding whose `check_id` matches the skill's `applies_to` list.
- `scan_enrichment` — the skill participates in the optional post-scan LLM enrichment pass that produces narrative findings descriptions.

Most skills declare both triggers. A skill with an empty `applies_to` list and only the `remediation` trigger acts as a global behavioural rule — for example a `general-pr-style` skill that prescribes the tone of every PR body the agent opens.

## Toggling skills per customer

Each customer keeps an `enabled` flag per skill. The default for built-in skills is on; custom skills inherit the flag set when they were created. Toggling happens on the Settings → Skills page, which lists every effective skill for the selected customer alongside a switch. The flag is a single boolean — there is no force-on state at the customer level.

## Per-connection overrides

A platform connection can override the customer-level toggle on a per-skill basis. This is useful when a customer has, for example, a sandbox GitHub org where you want a stricter set of skills active than for the production org.

The override is tri-state: *default* (inherit the customer toggle), *force on* (this connection always uses the skill, regardless of the customer toggle), or *force off* (this connection always skips the skill). Overrides are stored as a sparse `{skill_name: bool}` map on the connection row, so a skill that is not mentioned simply inherits the customer default. Clearing the dict removes every override on that connection.

> Per-connection overrides are stored on the connection record itself, so they survive a re-import of customer-level toggles.

## Authoring a custom skill

From the Settings → Skills page, click **+ New skill**. The drawer collects:

- `name` — URL-safe slug, 3–64 characters, lowercase letters, digits, and hyphens.
- `description` — a one-sentence summary shown in the table view.
- `category` — one of the 16 scanner-category keys or `general`.
- `applies_to_check_ids` — a multi-select picker bound to the live scanner registry; unknown IDs are rejected at save time.
- `triggers` — at least one of `remediation`, `scan_enrichment`.
- `body` — the markdown body. Keep it focused on one convention; combine multiple short skills rather than writing a single sprawling document.

The save endpoint validates the payload against the scanner registry before writing. If your `applies_to` list includes a check that has been retired, the request fails with a 400 and a list of unknown IDs.

## Browse the library

The full catalogue is available at [/help/skills-lib](/help/skills-lib). That page calls the read-only `/api/skills-registry` endpoint and renders each skill's frontmatter plus body in a drawer. It is read-only — to enable or disable, use Settings → Skills.

## Audit trail

Every skill body that influenced a prompt is hashed into the agent run's `AgentStep.prompt_hash`. The hash is deterministic from the concatenated operator template SHA plus each selected skill's content SHA, in selection order. This means an auditor can verify, post hoc, exactly which skills were active during a remediation by replaying the registry and comparing hashes against the stored value. See [Compliance & audit](/help/compliance) for the wider audit-log story.
