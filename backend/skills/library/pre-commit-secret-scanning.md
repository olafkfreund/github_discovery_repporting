---
name: pre-commit-secret-scanning
description: Configures pre-commit hooks for local secret scanning before commits reach the remote repository.
category: secrets_mgmt
applies_to:
  - SEC-004
  - SEC-005
triggers:
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - pre-commit
  - secrets
  - hooks
---

# Pre-Commit Secret Scanning

Catching secrets at commit time — before they reach the remote — is significantly
cheaper than rotating credentials after they appear in history.  Pre-commit hooks
provide this local gate with minimal setup.

## Prerequisites

```bash
pip install pre-commit
# or via pipx
pipx install pre-commit
```

## .pre-commit-config.yaml

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4   # pin to a specific release; update via `pre-commit autoupdate`
    hooks:
      - id: gitleaks

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: detect-private-key
      - id: detect-aws-credentials
        args: [--allow-missing-credentials]
```

## Activating in a Repository

```bash
# Install hooks for this repository (run once per clone).
pre-commit install

# Optional: install as a pre-push hook rather than pre-commit
# to avoid interrupting developers on every WIP commit.
pre-commit install --hook-type pre-push
```

## CI Enforcement

Local hooks are advisory — developers can bypass them with `git commit --no-verify`.
Pair local hooks with a CI-level scan job to ensure coverage:

```yaml
jobs:
  secret-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history for --all scan
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Handling False Positives

When a pattern is a known non-secret (e.g. a test fixture), use an inline annotation
rather than suppressing the entire rule:

```python
# gitleaks:allow
EXAMPLE_TOKEN = "EXAMPLE_abc123"  # used only in unit tests
```

This limits the suppression to a single line rather than modifying the global allowlist.

## Team Adoption

- Include `pre-commit install` in your repository's `README` setup instructions.
- Add a CI job that runs `pre-commit run --all-files` to enforce the hook configuration
  against the full codebase rather than just changed files.
- Set `default_stages: [commit, push]` at the top level to run all hooks on both
  events by default, then override per-hook for slow checks.
