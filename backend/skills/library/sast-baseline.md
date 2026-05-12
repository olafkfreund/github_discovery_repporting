---
name: sast-baseline
description: Establishes a baseline SAST tool configuration covering both code scanning and secrets detection for a repository.
category: sast
applies_to:
  - SAST-001
  - SAST-002
triggers:
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - sast
  - security
  - scanning
---

# SAST Baseline Configuration

Static Application Security Testing (SAST) tools analyse source code without running
it to identify security vulnerabilities, code quality issues, and compliance deviations.
This skill describes a minimum viable SAST baseline for a new or existing repository.

## Tool Selection

For most teams, run at minimum:

1. **Language-specific SAST** — CodeQL (GitHub-native), Semgrep (open-source,
   multi-language), or Bandit (Python-specific).
2. **Secrets detection** — Gitleaks or truffleHog (see `gitleaks-config-conventions`
   skill for configuration guidance).

These two categories are complementary and should both be active in CI.

## Semgrep Baseline

Semgrep supports 30+ languages and has a curated rule registry.

```yaml
# .semgrep.yml — project-level configuration.
rules:
  - id: placeholder  # This file is required for --config .semgrep.yml to work.
    pattern: "placeholder"
    message: "placeholder"
    languages: [python]
    severity: INFO
```

```yaml
# .github/workflows/semgrep.yml
name: Semgrep SAST

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  semgrep:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      contents: read
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

      - name: Run Semgrep
        uses: semgrep/semgrep-action@v1
        with:
          config: >-
            p/default
            p/owasp-top-ten
            p/secrets
          generateSarif: "1"

      - name: Upload SARIF results
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: semgrep.sarif
```

## Bandit (Python)

```yaml
name: Bandit SAST

on: [push, pull_request]

jobs:
  bandit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - run: pip install bandit[toml]
      - run: bandit -r src/ -f sarif -o bandit.sarif --exit-zero
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: bandit.sarif
```

Configure Bandit via `pyproject.toml`:

```toml
[tool.bandit]
exclude_dirs = ["tests", "scripts"]
skips = ["B101"]  # assert statements — acceptable in test code
```

## SARIF Upload

Upload SARIF results to the GitHub Security tab using `github/codeql-action/upload-sarif`.
This centralises findings from multiple tools in one view without requiring a separate
SAST platform subscription.

## Baseline Suppression

When onboarding SAST to an existing codebase, use suppression annotations to silence
known-accepted findings so that new findings are visible immediately:

```python
result = subprocess.run(cmd, shell=True)  # nosec B602 — shell=True intentional here
```

Document each suppression with a rationale.  Review suppressions quarterly.
