---
name: pr-size-and-cadence
description: Provides guidance on keeping pull requests small and frequent to improve review quality and reduce integration risk.
category: sdlc_process
applies_to:
  - SDLC-004
triggers:
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - pull-request
  - sdlc
  - continuous-integration
---

# Pull Request Size and Cadence

Large pull requests are the primary cause of superficial code review.  Reviewers faced
with 500+ line diffs either skip detail or block on them entirely.  Small, focused PRs
are reviewed faster, catch more issues, and reduce merge conflict frequency.

## Size Targets

| Category | Lines Changed (approx.) |
|---|---|
| Ideal | Under 200 |
| Acceptable | 200-400 |
| Requires justification | 400-800 |
| Should be split | Over 800 |

These are guidelines, not hard limits.  A 600-line PR that renames a module is less
risky than a 150-line PR that changes authentication logic.  Use context and judgment.

## Splitting Strategies

### Feature flags

Deploy code that is unreachable behind a feature flag.  Merge the flag infrastructure
first, then the implementation, then the flag activation.  This decouples deploy from
release and allows incremental review.

### Preparatory refactoring

If implementing a feature requires refactoring existing code first, create two PRs:
one for the refactoring (no behaviour change) and one for the feature.  This makes
each PR independently reviewable.

### Vertical slices

Decompose by user-visible behaviour rather than layer.  A "user can upload an avatar"
feature produces smaller PRs than "implement the storage layer", "implement the API",
"implement the UI" in sequence — because the slice PRs are independently deployable.

## Commit Hygiene

Small PRs are easier to achieve when individual commits are also focused:

- One logical change per commit.
- Commit messages that explain *why*, not *what*.
- No "fix tests", "typo", "wip" commits in the final branch — squash or amend
  before raising the PR.

## Cadence

Aim to merge at least one PR per engineer per day.  This creates a forcing function
that drives PR size down naturally: if you must merge daily, you must keep changes small.

Track PR merge frequency per team.  A drop in frequency often signals a large "epic
branch" accumulating changes that will eventually produce a monster merge conflict.

## Measuring PR Size Over Time

```bash
# Count lines changed per merged PR in the last 30 days.
gh pr list --state merged --limit 100 --json number,additions,deletions \
  --jq '[.[] | {number, changed: (.additions + .deletions)}] | sort_by(.changed) | reverse'
```

Review this output monthly.  When the median grows above 400 lines, discuss splitting
strategies in the team retrospective.
