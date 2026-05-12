---
name: workflow-pinned-actions
description: Explains why and how to pin GitHub Actions to full commit SHAs to prevent supply-chain attacks.
category: cicd
applies_to:
  - CICD-005
  - CICD-006
triggers:
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - github-actions
  - supply-chain
  - pinning
---

# Workflow Action Pinning

Referencing a GitHub Action by mutable tag (e.g. `actions/checkout@v4`) means the
workflow runs whatever commit the tag currently points to.  Tag owners can push new
commits under an existing tag, introducing malicious code into your CI pipeline
without any change to your workflow file.  Pinning to a full commit SHA eliminates
this risk.

## The Problem

```yaml
# Vulnerable: the `v4` tag can be moved to any commit at any time.
- uses: actions/checkout@v4
```

```yaml
# Safe: this specific commit SHA is immutable.
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
```

## Tooling

Managing SHA pins manually is impractical.  Use one of these tools to automate:

### Dependabot (recommended for most teams)

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    # Dependabot will open PRs to update pinned SHAs when new releases appear.
```

### pin-github-action (one-shot migration)

```bash
pip install pin-github-action
pin-github-action .github/workflows/*.yml
```

This rewrites all tag references in your workflow files to their current SHA,
adding the tag as a comment for human readability.

### Mend Renovate

Renovate supports GitHub Actions pinning with the `pinDigests` option in your
`renovate.json`:

```json
{
  "extends": ["config:base"],
  "pinDigests": true
}
```

## Exceptions

First-party GitHub actions (`actions/*`, `github/*`) are lower-risk because they are
controlled by GitHub Inc., but they are not immune to compromise.  Apply SHA pinning
consistently regardless of action owner.

## Verification

```bash
# Find workflow files with unpinned actions.
grep -r "uses:" .github/workflows/ | grep -v '@[0-9a-f]\{40\}'
```

A clean output (no lines printed) means all actions are pinned.

## After Pinning

Update pinned SHAs regularly.  Set up Dependabot (shown above) or a scheduled Renovate
run so that security patches in actions are applied promptly without manual effort.
