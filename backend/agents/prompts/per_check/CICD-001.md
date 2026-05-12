# CICD-001 — CodeQL workflow

You are remediating finding **CICD-001** ({severity}) on {repo_name}.

Add a CodeQL workflow that runs on push to {default_branch} and on a weekly schedule.

## Required action

1. Use `write_file` to create `.github/workflows/codeql.yml` with content:

   ```yaml
   name: CodeQL

   on:
     push:
       branches: ["{default_branch}"]
     pull_request:
       branches: ["{default_branch}"]
     schedule:
       - cron: "0 6 * * 0"

   jobs:
     analyze:
       name: Analyze ({{{{ matrix.language }}}})
       runs-on: ubuntu-latest
       permissions:
         actions: read
         contents: read
         security-events: write
       strategy:
         fail-fast: false
         matrix:
           language: [{primary_language}]
       steps:
         - uses: actions/checkout@v4
         - uses: github/codeql-action/init@v3
           with:
             languages: ${{{{ matrix.language }}}}
         - uses: github/codeql-action/analyze@v3
   ```

   The `{primary_language}` placeholder is provided in the user prompt (e.g.
   "python", "javascript"). If absent, default to "python".

2. Call `run_command` with `["yamllint", ".github/workflows/codeql.yml"]` to
   sanity-check syntax. Read the result; if errors, fix and retry once.

3. Call `recipe_success_check` with `check_id="CICD-001"`.

4. Return a final message.

Allowed files only: `.github/workflows/codeql.yml`.
