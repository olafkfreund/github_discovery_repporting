---
name: pr-review-policy
description: Defines a pull request review policy that balances velocity with quality gates and applies to SDLC and collaboration checks.
category: sdlc_process
applies_to:
  - SDLC-001
  - SDLC-003
  - COLLAB-006
triggers:
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - pull-request
  - review
  - sdlc
---

# Pull Request Review Policy

A documented and consistently applied review policy reduces integration risk while
keeping delivery cadence predictable.  This skill describes the elements of an
effective policy and how to enforce them mechanically.

## Policy Elements

### Minimum Reviewer Count

Require at least one non-author review before merging.  For repositories containing:

- Customer-facing APIs or authentication code — require two reviewers.
- Infrastructure-as-code affecting production — require the infrastructure team lead
  plus one peer.
- Documentation only — self-merge is acceptable after passing CI.

### Review Scope

Reviewers should check:

1. **Correctness** — does the change do what the description says?
2. **Test coverage** — are new code paths exercised by tests?
3. **Security** — does the change introduce injection points, hardcoded secrets, or
   overly permissive access controls?
4. **Dependency changes** — are new dependencies vetted and version-pinned?
5. **Breaking changes** — are API contracts, database migrations, and message formats
   backward-compatible?

### Staleness

Dismiss stale approvals when new commits are pushed.  This prevents the "approved-then-
amended" pattern where a reviewer approves a clean diff but the author subsequently adds
unreviewed changes before merging.

### Draft PRs

Encourage the use of draft PRs for work in progress.  Draft status signals that the
branch is not ready for review and allows early feedback without creating review-request
noise.

## GitHub Branch Protection Settings

```json
{
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "require_last_push_approval": true
  }
}
```

`require_last_push_approval` ensures that the author cannot approve their own last
push, even if they are in the CODEOWNERS file.

## Review Turnaround SLA

Define and publish a review turnaround expectation.  A common target:

- **Initial review response:** within one business day of review request.
- **Re-review after changes:** within four hours of the author marking the PR ready.

Teams with async-first cultures may adjust these targets, but they should be explicit
and tracked.

## Measuring Review Health

Track these metrics monthly:

- Median time from PR opened to first review.
- Median time from first review to merge.
- Percentage of PRs merged without any review (target: 0%).

A rising "time to first review" metric indicates bottlenecks (too few reviewers, PRs
too large) that should be addressed before they impact delivery cadence.
