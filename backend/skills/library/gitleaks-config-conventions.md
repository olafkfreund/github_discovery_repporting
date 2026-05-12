---
name: gitleaks-config-conventions
description: Defines conventions for configuring Gitleaks to detect secrets in the repository while minimising false positives.
category: secrets_mgmt
applies_to:
  - SEC-003
  - SEC-001
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - gitleaks
  - secrets
  - scanning
---

# Gitleaks Configuration Conventions

Gitleaks is the most widely adopted open-source tool for detecting accidentally committed
secrets.  A well-tuned `.gitleaks.toml` reduces alert fatigue while keeping detection
sensitivity high.

## File Location

Place the configuration at the repository root as `.gitleaks.toml`.  This path is
detected automatically by all major CI integrations and the `pre-commit` hook.

## Baseline Configuration

```toml
title = "Gitleaks configuration"

[extend]
# Extend the upstream default ruleset — never replace it from scratch.
useDefault = true

[allowlist]
description = "Global allowlist for known non-secrets"
regexes = [
  # Example: test fixtures that deliberately contain secret-shaped strings.
  "EXAMPLE_SECRET_PLACEHOLDER",
]
paths = [
  # Generated lock files — no secrets expected, but can trigger PKCE token rules.
  "package-lock.json",
  "poetry.lock",
  "Cargo.lock",
]

[[rules]]
# Custom rule example: internal API key format.
id          = "internal-api-key"
description = "Detects internal service API keys (prefix INT_KEY_)"
regex       = '''INT_KEY_[A-Za-z0-9]{32}'''
tags        = ["internal", "api-key"]
```

## Key Conventions

1. **Always extend the upstream default** (`useDefault = true`) rather than writing rules
   from scratch.  The upstream ruleset covers 150+ secret patterns maintained by the
   community.
2. **Add organisation-specific patterns** for custom credential formats (internal API key
   prefixes, service account token shapes) as additional `[[rules]]` blocks.
3. **Use `allowlist.paths`** to exclude generated files that are known safe (lock files,
   compiled assets, vendored dependencies).  Do not use `allowlist.regexes` for
   broad patterns — this permanently disables detection for that pattern everywhere.
4. **Keep `entropy` threshold above 3.5** if you enable entropy scanning — lower values
   produce an unworkable false-positive rate on Base64-encoded config values.
5. **Pin the Gitleaks version** in CI to a specific release tag.  The upstream releases
   occasionally change default rule IDs, which breaks per-rule suppressions.

## Running Locally

```bash
# Scan the entire commit history.
gitleaks detect --source . --log-opts="--all"

# Scan only uncommitted changes (pre-push hook use case).
gitleaks protect --staged
```

## CI Integration

```yaml
- name: Gitleaks secret scan
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    GITLEAKS_LICENSE: ${{ secrets.GITLEAKS_LICENSE }}
```

The action automatically reads `.gitleaks.toml` when present.
