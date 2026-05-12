# REPO-001 — Branch protection on default branch

You are remediating finding **REPO-001** (Critical) on {repo_name}.

The default branch ({default_branch}) currently has insufficient protection.

## Required action

This finding is a platform-settings change, NOT a file edit. You MUST:

1. Call `provider_api` with method `set_branch_protection`, args:
   ```json
   {{
     "repo": "<NormalizedRepo serialization>",
     "branch": "{default_branch}",
     "rules": {{
       "require_pull_request_review": true,
       "required_reviewer_count": 1,
       "enforce_admins": true,
       "allow_force_pushes": false,
       "allow_deletions": false
     }}
   }}
   ```
2. Call `recipe_success_check` with `check_id="REPO-001"` to verify.
3. Return a final message confirming the change.

You MUST NOT modify any file in the repo. `max_files_changed=0`.
