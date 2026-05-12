---
name: codeql-workflow-pattern
description: Provides a production-ready GitHub Actions workflow pattern for CodeQL static analysis.
category: cicd
applies_to:
  - CICD-001
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - codeql
  - sast
  - github-actions
---

# CodeQL Workflow Pattern

CodeQL is GitHub's semantic code analysis engine.  It scans for security vulnerabilities
by building a queryable database of the codebase and running curated queries against it.
The workflow below is the recommended starting point for most repositories.

## Complete Workflow

```yaml
name: CodeQL Analysis

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    # Run weekly on Sunday at 02:00 UTC regardless of push activity.
    - cron: "0 2 * * 0"

jobs:
  analyze:
    name: Analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read

    strategy:
      fail-fast: false
      matrix:
        language:
          - python
          # Add: javascript, typescript, java, csharp, go, ruby, swift, kotlin
          # as appropriate for this repository.

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          # Use the security-extended query suite for broader coverage.
          queries: security-extended

      - name: Autobuild
        uses: github/codeql-action/autobuild@v3

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
        with:
          category: "/language:${{ matrix.language }}"
```

## Key Decisions

1. **Use `security-extended` queries** — the default `security` suite omits a number
   of medium-severity queries that are valuable for catching injection vectors and
   path-traversal issues.
2. **Schedule weekly runs** — ensures that newly published queries flag existing code
   even when no commits occur.  Without a schedule, dormant repositories never get
   re-analyzed.
3. **Set `fail-fast: false`** on the matrix — prevents a build failure in one language
   from masking results in another.
4. **Scope `permissions` narrowly** — `security-events: write` is needed to upload
   SARIF results; `contents: read` satisfies the checkout step.  Avoid `write-all`.

## Autobuild Limitations

Autobuild works for most interpreted languages (Python, JavaScript, Ruby) without
configuration.  For compiled languages (Java, C#, Go), autobuild may fail if the
build system requires environment variables or toolchain versions beyond the default.
In that case, replace the autobuild step with explicit build commands:

```yaml
- name: Build
  run: mvn compile -DskipTests
```

## Suppressing Known False Positives

Use `// lgtm[js/sql-injection]` (LGTM inline comments) or CodeQL `@Suppress` annotations
in the source.  Do not disable entire query suites to silence one noisy rule.
