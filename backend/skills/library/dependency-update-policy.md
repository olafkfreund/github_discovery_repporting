---
name: dependency-update-policy
description: Establishes a dependency update policy using automated tools to reduce vulnerability exposure from outdated packages.
category: dependencies
applies_to:
  - DEP-002
  - DEP-005
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - dependencies
  - renovate
  - dependabot
  - supply-chain
---

# Dependency Update Policy

Outdated dependencies are one of the most common sources of known vulnerabilities.
An explicit, automated update policy ensures that security patches are applied promptly
without creating disruptive manual processes.

## Policy Framework

Define and publish the following for every repository:

1. **Update frequency** — how often automated PRs are raised (daily for security
   patches, weekly for routine updates).
2. **Auto-merge scope** — which update types are safe to merge without human review
   (patch-level security fixes, minor tool version bumps with pinned major versions).
3. **Blocking updates** — major version upgrades that require manual testing and
   sign-off before merging.
4. **SLA for critical CVEs** — security patches for critical and high severity
   vulnerabilities should be merged within 48 hours of the automated PR being raised.

## Renovate Configuration (recommended)

Renovate provides the most granular control over automated dependency updates.

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended"],
  "packageRules": [
    {
      "matchUpdateTypes": ["patch"],
      "matchCurrentVersion": "!/^0/",
      "automerge": true,
      "automergeType": "pr"
    },
    {
      "matchDepTypes": ["devDependencies"],
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": true
    },
    {
      "matchPackagePatterns": [".*"],
      "matchUpdateTypes": ["major"],
      "automerge": false,
      "labels": ["dependency-major"]
    }
  ],
  "vulnerabilityAlerts": {
    "enabled": true,
    "automerge": true
  },
  "schedule": ["before 9am on Monday"]
}
```

## Dependabot (simpler alternative)

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
    open-pull-requests-limit: 10

  - package-ecosystem: npm
    directory: /frontend
    schedule:
      interval: weekly
    open-pull-requests-limit: 10

  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

## Vulnerability Monitoring

Enable GitHub's Dependabot security alerts and Dependabot security updates (these are
separate settings):

- **Security alerts** — notify when a dependency has a known CVE.
- **Security updates** — automatically raise a PR to update the vulnerable package.

For language ecosystems not covered by Dependabot, consider:

- `osv-scanner` for broad ecosystem coverage.
- `trivy fs .` for filesystem-level scanning including indirect dependencies.

## Verification

```bash
# Check for known vulnerabilities in the current dependency set.
pip-audit                      # Python
npm audit                      # Node.js
cargo audit                    # Rust
bundle-audit                   # Ruby
```

Run these as a CI step separate from the automated update flow to catch vulnerabilities
in the time window between updates.
