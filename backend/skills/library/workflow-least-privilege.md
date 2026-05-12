---
name: workflow-least-privilege
description: Applies least-privilege GITHUB_TOKEN permissions to GitHub Actions workflows to limit blast radius of compromised jobs.
category: cicd
applies_to:
  - CICD-007
  - CICD-010
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - github-actions
  - least-privilege
  - iam
---

# Workflow Least-Privilege Permissions

By default, `GITHUB_TOKEN` is granted `write` access to most repository scopes in many
organization configurations.  A compromised workflow step that obtains the token can
push commits, open pull requests, create releases, or exfiltrate repository data.
Restricting permissions to the minimum required by each job limits the blast radius.

## Repository-Level Default

Set the organization and repository default to read-only:

**Settings > Actions > Workflow permissions > Read repository contents and packages**

This is the safest baseline.  Individual workflows then request only the scopes they
actually need.

## Workflow-Level Restriction

```yaml
# Deny all permissions at the workflow level, then grant only what is needed per job.
permissions: {}

jobs:
  build:
    permissions:
      contents: read   # checkout only
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - run: make build

  publish:
    permissions:
      contents: write    # push release tag
      packages: write    # push to GHCR
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - run: make release
```

## Common Scope Requirements

| Job Type | Required Scopes |
|---|---|
| Checkout only | `contents: read` |
| CodeQL upload | `security-events: write`, `actions: read`, `contents: read` |
| PR comment | `pull-requests: write` |
| Package publish | `packages: write`, `contents: read` |
| Deployment status | `deployments: write` |
| Issue label | `issues: write` |

## Preventing Token Leakage

1. **Never print `GITHUB_TOKEN` in workflow logs** — `echo $GITHUB_TOKEN` is caught by
   GitHub's secret scanning, but variables substituted via `${{ secrets.GITHUB_TOKEN }}`
   in `run:` steps may still appear if the shell expands them before masking applies.
2. **Set `GITHUB_TOKEN` as an environment variable per-step** rather than passing it
   through `run:` arguments to reduce the exposure window.
3. **Use `permissions: {}` at the workflow level** and only open scopes at the job level.
   This prevents a new job added later from accidentally inheriting broad permissions.

## Third-Party Actions

Third-party actions that request `GITHUB_TOKEN` via `secrets.GITHUB_TOKEN` inherit the
job-level permissions.  Pin such actions to a SHA and review their source code for
unexpected token usage before granting elevated scopes.
