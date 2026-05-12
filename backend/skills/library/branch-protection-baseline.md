---
name: branch-protection-baseline
description: Establishes minimum branch protection rules for the default branch to prevent direct pushes and require review.
category: repo_governance
applies_to:
  - REPO-001
  - REPO-002
  - REPO-003
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - branch-protection
  - governance
---

# Branch Protection Baseline

The default branch of every repository should be protected against direct force-pushes
and unreviewed merges.  This skill captures the minimum viable ruleset that satisfies
REPO-001 (default branch protection enabled), REPO-002 (at least one required reviewer),
and REPO-003 (status checks required before merging).

## Minimum Ruleset

Apply the following settings to your default branch (usually `main` or `master`):

1. **Require pull request reviews before merging** — set `required_approving_review_count`
   to at least 1.  For higher-risk repositories used in production deployments, prefer 2.
2. **Dismiss stale pull request approvals** — when new commits are pushed to the branch,
   previous approvals are automatically dismissed.  This prevents an approved-then-modified
   PR from being merged without re-review.
3. **Require status checks to pass** — name the CI workflow jobs explicitly rather than
   using a wildcard.  Wildcard matching silently passes if no job matches.
4. **Require branches to be up to date before merging** — prevents a race condition where
   two PRs pass CI independently but conflict on the protected branch.
5. **Do not allow bypassing the above settings for administrators** — administrator bypass
   is a common audit finding; disable it unless there is an explicit incident-response
   justification.

## GitHub API Example (via gh CLI)

```bash
gh api repos/{owner}/{repo}/branches/main/protection \
  --method PUT \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field required_status_checks='{"strict":true,"contexts":["ci/build","ci/test"]}' \
  --field enforce_admins=true \
  --field restrictions=null
```

Replace `ci/build` and `ci/test` with the actual check names reported in the pull
request's Status section.

## Terraform (GitHub Provider)

```hcl
resource "github_branch_protection" "main" {
  repository_id                   = github_repository.this.node_id
  pattern                         = "main"
  require_conversation_resolution = true
  enforce_admins                  = true

  required_pull_request_reviews {
    required_approving_review_count = 1
    dismiss_stale_reviews           = true
  }

  required_status_checks {
    strict   = true
    contexts = ["ci/build", "ci/test"]
  }
}
```

## Common Mistakes

- Setting `enforce_admins = false` — this creates a privileged bypass route that is
  frequently exploited during incidents when engineers push directly to avoid a slow CI
  pipeline.
- Using the `contexts` list with job names that change between workflow runs (e.g.
  matrix entries with dynamic naming); use a stable, named job instead.
- Forgetting to protect release branches (e.g. `release/*`) in addition to `main`.

## Verification

After applying, open the repository's **Settings > Branches** page and confirm the
protection rule shows as active.  Run a test PR that deliberately fails a status check
and confirm the merge button is disabled.
