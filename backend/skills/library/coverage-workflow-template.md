---
name: coverage-workflow-template
description: Provides a GitHub Actions workflow template that enforces a minimum test coverage threshold and uploads results.
category: code_quality
applies_to:
  - CQ-004
  - CQ-001
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - coverage
  - testing
  - github-actions
---

# Coverage Enforcement Workflow Template

Tracking test coverage at the CI level provides an objective quality gate and prevents
coverage regressions from being silently merged.  This template enforces a minimum
threshold and uploads results for trend tracking.

## Python (pytest-cov)

```yaml
name: Test Coverage

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests with coverage
        run: |
          pytest --cov=src \
                 --cov-report=xml \
                 --cov-report=term-missing \
                 --cov-fail-under=80

      - name: Upload coverage report
        uses: codecov/codecov-action@v4
        with:
          files: coverage.xml
          fail_ci_if_error: true
          token: ${{ secrets.CODECOV_TOKEN }}
```

## JavaScript / TypeScript (Jest)

```yaml
      - name: Run tests with coverage
        run: npx jest --coverage --coverageThreshold='{"global":{"lines":80}}'

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: coverage/lcov.info
```

## Threshold Guidance

| Project Stage | Recommended Minimum |
|---|---|
| New greenfield | 80% |
| Active product | 70% |
| Legacy (brownfield) | 50% (ratchet upward by 5% per quarter) |
| Security-critical code | 90% |

Set `--cov-fail-under` (pytest) or Jest `coverageThreshold` to enforce the minimum.
The CI job fails when coverage drops below the threshold, blocking the merge.

## Ratcheting

To prevent regressions without requiring a large upfront investment, use a "ratchet"
approach:
1. Record current coverage percentage as a baseline.
2. Fail CI only when coverage drops below the baseline.
3. Update the baseline when coverage genuinely improves.

`diff-cover` is a useful tool for Python that only measures coverage on changed lines:

```bash
pip install diff-cover
coverage xml
git diff origin/main...HEAD > diff.patch
diff-cover coverage.xml --diff=diff.patch --fail-under=90
```

## Badge

Add a coverage badge to your README to make the metric visible:

```markdown
[![Coverage](https://codecov.io/gh/org/repo/branch/main/graph/badge.svg)](https://codecov.io/gh/org/repo)
```
