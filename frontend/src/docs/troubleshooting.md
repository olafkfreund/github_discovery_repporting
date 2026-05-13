---
slug: troubleshooting
title: Troubleshooting
category: reference
order: 20
summary: Common failure modes for scans, agent runs, reports, and connection tests, with the first thing to check for each.
audience: [admin]
last_reviewed: 2026-05-13
---

# Troubleshooting

This page catalogues the failure modes operators see most often and the first thing to check for each. If a symptom is not listed, start from the backend logs and filter by the relevant `scan_id`, `agent_run_id`, or `connection_id`.

## Scan issues

### Scan stuck in `running`

Most often this is one of two things: a very long repo-enumeration tail (large orgs with thousands of repos), or a rate-limited PAT. Check the backend log for warnings from the provider layer — GitHub returns a `secondary rate limit` header that the scanner respects.

> If a scan has been `running` for more than an hour with no log activity, mark it `failed` directly in the database and retry the scan with a fresh PAT. The next run will be a clean attempt.

### Scan completes with zero findings

Two probable causes: the connection points at an empty org, or the PAT lacks the scopes needed to enumerate repos. Verify with `GET /api/connections/{id}` and `POST /api/connections/{id}/validate`. A passing validation but zero findings is usually an empty org.

### "Repository access denied" in the scan log

The PAT is missing a scope. Required scopes per provider:

| Provider | Required scopes |
|---|---|
| GitHub | `repo` (read), `read:org`, `read:user` |
| GitLab | `read_api`, `read_repository` |
| Azure DevOps | `Code (read)`, `Build (read)`, `Project and team (read)` |

Issue a fresh PAT with the missing scope and update the connection. The connection encryption layer means you must re-enter the credential; the existing value cannot be patched in place without going through the update endpoint.

## Agent run issues

### Run rejected with 403 "kill switch engaged"

The exact message is `Kill switch engaged at <layer> layer; cannot create agent runs.` where `<layer>` is either `global` or `customer`.

- Layer `global`: someone has set `global_kill_switch_enabled` to true on the global settings singleton. Disable from `/settings/global`.
- Layer `customer`: the customer's `RemediationPolicy` row has `kill_switch_enabled` set to true. Disable from `/settings/remediation-policy` for that customer.

### Run rejected with 409 "monthly cost cap exceeded"

The exact message is `Monthly cost cap exceeded for customer: spent $<spent> of $<cap>.` The cost-cap service sums every completed agent-step cost for the current calendar month and rejects new runs once the sum reaches the cap.

Options: wait for the next month rollover, raise the cap on the customer's `RemediationPolicy`, or pause agent runs while you review the spend trend on the customer detail page.

### Run rejected with 409 "scan not completed"

The exact message is `Scan <id> is in state '<status>'; remediation requires status 'completed'.` Wait for the scan to finish before triggering the agent.

### Run stuck in `dispatched` (CI runtime mode)

This means the agent run was created with `runtime_mode='ci'` and the BPS backend dispatched the CI workflow, but no events have come back. Check the CI run on the customer's platform to confirm it actually started. The most common cause is the configured workflow repository or workflow filename being wrong — the dispatch endpoint will not retry.

### Webhook signature mismatch for CI-mode events

Each agent run carries a `callback_secret` that the runner must use to HMAC-SHA256 the request body. The BPS endpoint at `POST /api/agent-runs/{id}/events` returns 401 if the `X-Hub-Signature-256` header is absent, malformed, or has a digest that does not match. Verify the runner is using the agent run's specific `callback_secret`, not a global environment value, and that it is signing the raw request bytes rather than a re-serialised JSON form.

## Report issues

### PDF download returns 404

The report has not been generated yet, or generation failed. Check `Report.status` via `GET /api/reports/{id}`. If status is `failed`, look in the backend logs for the WeasyPrint trace; the most common cause is missing system fonts.

### PDF renders with blank text blocks

WeasyPrint is finding the layout but failing to substitute fonts. Make sure the `liberation` font family is installed in the runtime image, or start the backend inside `nix develop` so the flake provisions the fonts automatically.

### Excel download 404

Same root cause as the PDF 404. The Excel renderer runs alongside the PDF renderer; if one fails the other usually does too. Inspect `Report.excel_path` — if it is null, the file was never written.

## Connection test failures

### 401 from `POST /connections/{id}/validate`

Bad credentials. The PAT has been revoked, has expired, or was mistyped on creation. Roll a fresh PAT and update the connection.

### 403 from validate

Credentials are valid but the scope is insufficient. See the per-provider scope table under [Scan issues](#scan-issues) above.

### TLS / certificate error

Self-hosted GitLab or Azure DevOps instances often use a private CA. Trust the CA in the BPS container — typically by mounting the PEM into `/etc/ssl/certs/` and running `update-ca-certificates` at image build time.

## Logs to check first

Start with the backend container's structured log. Useful filters:

- `agent_run_id=<uuid>` — every line for one run, including LLM calls.
- `scan_id=<uuid>` — every line for one scan, including per-repo enumeration.
- `connection_id=<uuid>` — every line for one connection, including the encryption layer.

For CI-mode failures also pull the workflow run output on the customer's CI platform; the runner emits the trace there before posting events back to BPS.
