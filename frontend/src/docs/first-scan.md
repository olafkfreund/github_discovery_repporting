---
slug: first-scan
title: Running your first scan
category: scans
order: 10
summary: How to trigger a scan, what each phase of the pipeline does, and how to interpret the status changes you see on the scan detail page.
audience: [end-user]
last_reviewed: 2026-05-13
---

Once you have created a customer and added a working platform connection, you are ready to run a scan. A scan is a point-in-time assessment of every repository visible to one connection. This page walks through how to trigger one, what BPS is doing behind the scenes, and what to do when something fails. The whole workflow is non-blocking — triggering a scan returns immediately and the UI polls for progress.

## Triggering a scan

From the customer detail page:

1. Click the **Run scan** button.
2. Pick the platform connection you want to scan. If the customer has only one, it is preselected.
3. Optional: pick a **Scan profile**. Leaving this empty runs the default 16-category coverage with all checks enabled and standard weights. Profiles let you toggle categories on or off and tune thresholds; see the section below for a brief overview.
4. Click **Start scan**. You are redirected to the scan detail page, which polls every few seconds for updates.

The equivalent API call is straightforward. The `profile_id` field is optional and may be omitted entirely.

```bash
curl -X POST http://localhost:8000/api/customers/550e8400-e29b-41d4-a716-446655440000/scans \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": "7c8f9d4a-1234-5678-90ab-cdef01234567",
    "profile_id": null
  }'
```

The response includes the new scan UUID and an initial status of `pending`:

```json
{
  "id": "9b2e3c4d-...",
  "customer_id": "550e8400-...",
  "connection_id": "7c8f9d4a-...",
  "status": "pending",
  "scan_config": null,
  "started_at": null,
  "completed_at": null,
  "total_repos": null
}
```

## What happens during a scan

BPS runs the scan pipeline in distinct phases. Understanding them helps when triaging a slow scan or a partial failure.

### Phase 1: organisation-level checks

BPS fetches organisation-level data (membership counts, two-factor enforcement, default repository permissions, whether a security policy is published), then runs the Platform Architecture and Identity and Access scanners against it. Org-level findings have no `scan_repo_id` and appear under their own section in the results UI. This phase is fast — typically under a second.

### Phase 2: repository enumeration

BPS lists every repository visible to the token. For GitHub it calls `org.get_repos()`; for GitLab `group.projects.list(include_subgroups=True)`; for Azure DevOps it iterates projects and then repositories per project. Results are normalised so the rest of the pipeline is platform-agnostic. Sensible circuit breakers apply — Azure DevOps stops after 500 projects to prevent runaway pagination.

### Phase 3: per-repository checks

For every repository, BPS fetches the assessment data needed by the 14 repo-level scanners (branch protection, CI workflow files, security toggles, file presence, recent PR metadata) and persists one finding per check.

Per-repo cost dominates scan duration. A small organisation of ten repositories takes around a minute end-to-end; a hundred repositories takes ten to fifteen minutes; very large estates can take an hour or more. Concurrency is bounded by the `MAX_CONCURRENT_SCANS` setting on the BPS server.

### Phase 4: scoring and report generation

After the last repository is scanned, the orchestrator computes per-category weighted scores. The AI analyser then generates an executive summary and prioritised recommendations, and BPS renders the PDF, Excel, and Zip-bundle reports. None of these steps re-contact the platform.

## Watching progress

The scan detail page polls the API every few seconds and updates the status indicator. There are four user-facing states.

| State | Backend value | What it means |
|---|---|---|
| Queued | `pending` | Scan record created. Waiting for a free concurrency slot. |
| Running | `scanning` | Pipeline executing. `started_at` is now set. |
| Completed | `completed` | All phases finished. `completed_at` and `total_repos` are set. Reports are downloadable. |
| Failed | `failed` | The pipeline threw an unrecoverable error. `error_message` describes the problem. |

> Note: A scan that finishes its org-level phase but then has trouble with a single repository will continue rather than fail the whole run. Individual repo errors are recorded as failed findings under that repo, not as a top-level scan failure.

If you reload the page after a scan completes, the polling stops and you are looking at a static results view; the URL is shareable.

## Scan profiles, briefly

The default scan covers all 16 categories at standard weights. A *scan profile* is a per-customer override that lets you disable entire categories, disable individual checks, override category weights, and tune per-check thresholds (for example `CICD-008.pass_threshold` or `IAM-003.max_admin_ratio`). Profiles are saved per customer, selected at scan trigger time, and snapshotted into the scan record so reruns are reproducible. Profile authoring is covered in the dedicated scan-profiles documentation page.

## Common scan failures

The status banner on a failed scan shows the error message produced by the pipeline. The four most common causes are listed below with the action that resolves each one.

### Authentication failed

> "Authentication failed — the access token is invalid or expired."

The PAT expired, was revoked, or was never valid. Edit the connection, paste a fresh token, click **Test connection** to confirm, and trigger the scan again.

### Access denied

> "Access denied — the token lacks the required scopes."

The token is valid but missing a scope. Regenerate it with the scopes listed in [Connecting GitHub, GitLab, and Azure DevOps](/help/platform-connections) and update the connection.

### Organisation or group not found

> "Organization or group not found. Verify that '<x>' is spelled correctly and the token has access to it."

Either a typo in the `org_or_group` field, or the token does not have any visibility into that organisation. GitLab in particular requires that the token's owning user has at least Reporter access to the group.

### Rate limit exceeded

> "API rate limit exceeded" (typically from GitHub).

The token's per-hour quota has been exhausted. Wait one hour, or supply a token with higher limits (for example a GitHub App token instead of a classic PAT). Re-trigger once the quota frees up — partial work from the failed run is not reused.

### Connection refused

> "Connection refused" or "Failed to resolve host"

The BPS server cannot reach the platform's base URL. Confirm the **Base URL** field, check for egress firewalls, and verify DNS resolves from the BPS server itself.

## See also

- [Glossary and concepts](/help/glossary) — what *Scan*, *Finding*, and *Scan Profile* mean.
- [Connecting GitHub, GitLab, and Azure DevOps](/help/platform-connections) — token scopes for each platform.
- [Reading scan results](/help/scan-results) — how to interpret the output once the scan completes.
- [Adding a customer](/help/customer-onboarding) — where customer records and connections come from.
