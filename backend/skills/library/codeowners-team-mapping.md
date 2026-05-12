---
name: codeowners-team-mapping
description: Guides correct authoring of CODEOWNERS files using team handles rather than individual usernames.
category: repo_governance
applies_to:
  - REPO-008
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - codeowners
  - governance
  - ownership
---

# CODEOWNERS — Team Mapping Guidance

When proposing or reviewing a CODEOWNERS file, the following rules reduce the risk of
silent ownership gaps as teams evolve.

## Authoring Rules

1. **Prefer team handles over individual usernames** — `@org/platform-eng` survives
   team membership changes; `@alice` becomes stale the day Alice leaves.
2. **Place a catch-all (`*`) at the top** — later, more specific glob patterns override
   it.  The ordering is last-match-wins, so the catch-all at the top is overridden by
   any subsequent pattern.
3. **Mirror the top-level directory layout** — every `src/`, `services/`, `apps/`
   subtree should have an explicit owner block.  Relying on the catch-all alone means
   any new top-level directory is silently owned by whoever owns `*`.
4. **Never list users who are not org members** — GitHub rejects CODEOWNERS files with
   unresolvable usernames and suppresses the review-request mechanism entirely for the
   affected paths.
5. **Keep total lines under 200** — if the file grows beyond this, split ownership
   using per-directory `.github/CODEOWNERS` overlays (supported on GitHub Enterprise).

## Minimal Example

```
# Catch-all: platform team owns everything not explicitly listed below.
*                          @org/platform-eng

# Services owned by domain-specific teams.
/services/billing/         @org/billing-eng
/services/auth/            @org/identity-eng

# Infrastructure-as-code reviewed by infra team and a senior engineer.
/terraform/                @org/infra-eng
/.github/                  @org/platform-eng @org/security-eng

# Documentation only needs a tech writer.
/docs/                     @org/tech-writing
```

## Anti-patterns

- **Individual usernames in catch-all position** — these break the moment the person
  leaves the team and create a single point of failure for review requests.
- **Overlapping patterns that conflict** — CODEOWNERS uses last-match-wins; an
  accidental re-ordering at line 200 silently disables a critical owner from line 50.
  Keep patterns non-overlapping where possible.
- **Empty CODEOWNERS file** — an empty file satisfies the "file exists" check but
  provides no actual protection.  Always include at least the catch-all line.

## How to Test

After authoring, push to a feature branch and observe that the GitHub pull request UI
shows the expected reviewer suggestions in the Reviewers panel.  If reviewers do not
appear, the file likely contains a syntax error or an unresolvable handle — GitHub
surfaces a warning icon next to the CODEOWNERS file in the repository view.

## Validation

```bash
# Basic syntax check via GitHub CLI (requires appropriate token scope).
gh api repos/{owner}/{repo}/codeowners/errors
```

A clean response (empty `errors` array) confirms all handles are resolvable.
