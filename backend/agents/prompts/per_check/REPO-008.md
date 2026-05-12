# REPO-008 — CODEOWNERS file present

You are remediating finding **REPO-008** ({severity}) on {repo_name}.

The repository has no CODEOWNERS file. Create one.

## Required action

1. Use `write_file` to create `.github/CODEOWNERS` with content:

   ```
   # Default owners for everything in the repo.
   # Replace with concrete team handles before review.
   *       @{customer_codeowner_team}
   ```

   The `{customer_codeowner_team}` placeholder is provided in the user prompt.
   If absent, use `@security-team` and note the substitution in your final message.

2. Call `recipe_success_check` with `check_id="REPO-008"`.

3. Return a final message confirming.

Allowed files only: `.github/CODEOWNERS`, `CODEOWNERS`, `docs/CODEOWNERS`.
