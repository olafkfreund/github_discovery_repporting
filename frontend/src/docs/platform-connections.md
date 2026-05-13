---
slug: platform-connections
title: Connecting GitHub, GitLab, and Azure DevOps
category: customers
order: 20
summary: The token scopes, base URLs, and quirks for each supported platform, plus how to test a connection before saving it.
audience: [end-user]
last_reviewed: 2026-05-13
---

A *platform connection* is the credential record that lets BPS talk to one DevOps platform on behalf of one customer. This page lists the supported platforms, the exact token scopes each one needs, and how to verify a new connection before saving it. You can create as many connections per customer as you like.

## Supported platforms

BPS currently supports three platforms behind a common provider interface, so the scanning workflow is identical regardless of which platform you connect. Bitbucket support is on the roadmap but not yet implemented.

| Platform | Auth method | Scope unit |
|---|---|---|
| GitHub (cloud or Enterprise Server) | Personal Access Token | Organisation |
| GitLab (gitlab.com or self-managed) | Personal or group access token | Group (with sub-group support) |
| Azure DevOps Services | Personal Access Token | Organisation |

## GitHub

GitHub uses a Personal Access Token (PAT). Both classic and fine-grained tokens work, with one caveat noted below.

### Required scopes

For read-only scanning (the default):

- `repo` — full repository access. Required because the scanner inspects branch protection and CI workflow files in private repos.
- `read:org` — read organisation membership. Required for the Identity and Access scanner.

For agentic remediation in `ci` runtime mode, add `workflow` (the agent runs as a dispatched GitHub Actions workflow). For branch-protection management or CODEOWNERS reads, optionally add `admin:org`.

A pre-checked URL for creating the right token:

```text
https://github.com/settings/tokens/new?scopes=repo,read:org,workflow&description=BPS%20scanner
```

> Tip: Click the link above with a logged-in browser. GitHub will pre-fill the scopes; you just choose the expiry and click **Generate token**.

### Org versus user scoping

The `org_or_group` field on a GitHub connection must be an organisation login, not a user login. BPS calls `GET /orgs/{org}` to validate the connection — pointing it at a user login (for example `octocat`) will fail with 404 even though the PAT is valid.

### GitHub Enterprise Server

For self-hosted GitHub Enterprise Server, populate the **Base URL** field with the API root, for example `https://github.example.com/api/v3`. BPS validates that the host is reachable over HTTPS and does not resolve to a private or reserved IP range; bypassing that check would be an SSRF risk.

### Fine-grained tokens

Fine-grained PATs work for scanning, but BPS cannot enumerate their scopes, so the `has_write_scope` flag stays "unknown" in the connection details. Classic PATs return their scopes in the `X-OAuth-Scopes` response header, so BPS can confirm `repo` and `workflow` are present.

## GitLab

GitLab accepts personal access tokens, project access tokens, and group access tokens. For organisation-scope scanning of a whole group, a personal access token (PAT) owned by a user with at least Reporter access to the group is the simplest choice.

### Required scopes

For read-only scanning:

- `read_api` — read access to the API. Required.
- `read_repository` — read repository contents. Required for the file-presence checks (CODEOWNERS, SECURITY.md, etc.).

For agentic remediation:

- `api` — full API access (covers both read and write), **or**
- both `read_repository` and `write_repository` together.

### Group path and self-managed instances

The `org_or_group` field must contain the GitLab full path. BPS resolves it tolerantly: a direct lookup is tried first, and on a 404 it falls back to a name search that matches case-insensitively against `full_path` or `name`. So entering `Acme` resolves to `acme-corp/acme` if that group exists. Sub-group support is built in — entering `acme/payments/backend` scans only that sub-group and its descendants.

For self-managed GitLab, populate the **Base URL** field with the instance root (for example `https://gitlab.example.com`). HTTPS is required and the host must not resolve to a private or reserved address.

> Note: Personal access tokens support the `/personal_access_tokens/self` endpoint, so BPS can read your scope list and report `has_write_scope` accurately. Group access tokens and deploy tokens do not support that endpoint, so `has_write_scope` stays unknown for them.

## Azure DevOps

Azure DevOps uses a Personal Access Token sent as HTTP Basic authentication with an empty username (`Authorization: Basic base64(":{pat}")`).

### Required scopes

For read-only scanning:

- **Code (Read)** — required for the repository content, file-presence, and branch-policy checks.
- **Build (Read)** — required for the CI/CD scanner to enumerate pipelines.
- **Project and Team (Read)** — required to list projects under the organisation.
- **Identity (Read)** — required for the Identity and Access scanner.

For agentic remediation, add **Code (Write)** and **Build (Read & Execute)**.

A concrete PAT scope checklist:

```json
{
  "scopes": [
    "vso.code",
    "vso.build",
    "vso.project",
    "vso.identity"
  ],
  "expires_in_days": 90,
  "display_name": "BPS scanner"
}
```

> Note: Azure DevOps does not expose a token-introspection endpoint that reliably returns scope assignments. BPS always reports `has_write_scope` as `None` for Azure DevOps connections. Insufficient permissions will surface as a 403 at write time rather than at validation time.

### Organisation URL

The `org_or_group` field is the organisation name as it appears in `dev.azure.com/<org>`. So if your URL is `https://dev.azure.com/acme-corp`, enter `acme-corp`. For Azure DevOps Server or `visualstudio.com` URLs, populate the **Base URL** field explicitly — the host must end in `dev.azure.com`, `visualstudio.com`, or `azure.com`.

## Adding a connection

From the customer detail page:

1. Click **Add connection** and choose the platform.
2. Enter a **Display name** — shown in the connection list and on scan records. Free-form, for example `Acme — main GitHub`.
3. Enter the **Organisation / Group** identifier as described in the platform-specific sections above.
4. Paste the **Personal Access Token**. The token is encrypted with Fernet before it touches the database.
5. Optional: populate the **Base URL** for self-hosted instances.
6. Click **Test connection** before saving — this makes a live call to the platform and surfaces errors before you commit the row.

## Testing a connection

The **Test connection** button calls `POST /api/connections/{id}/validate`. A successful test means BPS could reach the platform, authenticate with the stored credentials, and find the organisation or group. It updates `last_validated_at` on the connection and probes the write-scope status.

You will see one of three outcomes.

| Outcome | Meaning | What to do |
|---|---|---|
| `Connection credentials are valid.` | All good. `last_validated_at` is updated. | Save and trigger a scan. |
| `Authentication failed — the access token is invalid or expired.` | HTTP 401 from the platform. | Regenerate the PAT and update the connection. |
| `Group or organization '<x>' not found.` | HTTP 404. | Check spelling; for Azure DevOps confirm the org URL; for GitLab try the full path. |

> Tip: If `Test connection` works but a subsequent scan fails with "Access denied", the PAT is valid but lacks a required scope. Compare your token's scopes against the lists in the platform-specific sections above and regenerate with the missing scope added.

## See also

- [Glossary and concepts](/help/glossary) — definitions for *Platform Connection*, *Kill Switch*, and related terms.
- [Adding a customer](/help/customer-onboarding) — the prerequisite for connecting a platform.
- [Running your first scan](/help/first-scan) — what happens once a connection is in place.
- [Reading scan results](/help/scan-results) — how scan output is structured and presented.
