---
slug: customer-onboarding
title: Adding a customer
category: customers
order: 10
summary: How to create a customer record in BPS, what each field means, and what to set up next so the customer is ready to be scanned.
audience: [end-user]
last_reviewed: 2026-05-13
---

A *customer* in BPS is a tenant container: it owns its platform connections, scan history, scan profiles, remediation policy, LLM connections, agent instructions, and skills. You will create one customer per client organisation, or per internal business unit, and then attach everything else to it. This page walks through the workflow.

## Why customers?

BPS is multi-tenant by design. Every connection, scan, and report is associated with exactly one customer, which gives you four practical benefits.

First, reports can be branded and labelled per organisation without leaking data between tenants. Second, scan profiles and remediation policies can differ — a banking client may need stricter thresholds than an internal sandbox. Third, LLM connections are scoped per customer, so each tenant can use its own model provider and pay from its own budget. Fourth, the audit trail is naturally segmented; export a customer's full history without surfacing anyone else's findings.

If you are the only consumer of BPS, you will still want at least one customer record — there is no anonymous mode.

## Adding a customer

Adding a customer takes about thirty seconds. There are no required fields beyond the name.

1. Navigate to [/customers](/customers). You will see a table of existing customers (empty on a fresh install).
2. Click the **+ New customer** button at the top right.
3. Fill in the form:
   - **Name** — required. The display name shown in the sidebar, in reports, and on the dashboard. Use the organisation's preferred spelling, with spaces and proper case. See the naming conventions section below.
   - **Contact email** — optional. Stored as plain text. Useful when a report is sent externally and the recipient needs to know who to contact internally.
   - **Notes** — optional, free-form Markdown. Visible only inside BPS. A good place for short context such as "Migrated from Bitbucket March 2026" or "Single-tenant Azure DevOps Server install".
4. Click **Save**. You are redirected to the customer's detail page. The URL contains the customer's UUID, for example `/customers/550e8400-e29b-41d4-a716-446655440000` — that UUID is also the value used in the REST API.

The corresponding API call, if you ever need to script the same workflow:

```bash
curl -X POST http://localhost:8000/api/customers/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "contact_email": "security@acme.example",
    "notes": "Quarterly review cycle, primary contact is Jane Doe."
  }'
```

And here is what the response body looks like, which is also what the detail page calls when it loads:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Acme Corp",
  "slug": "acme-corp",
  "contact_email": "security@acme.example",
  "notes": "Quarterly review cycle, primary contact is Jane Doe.",
  "enable_scan_enrichment": false,
  "created_at": "2026-05-13T10:00:00Z",
  "updated_at": "2026-05-13T10:00:00Z"
}
```

> Note: The `slug` is derived from `name` automatically (lower-case, hyphens). You never need to set it manually, and renaming the customer updates the slug at the same time.

## Naming conventions

Names show up in three places that get read by people: the sidebar, scan reports, and the dashboard. A short, human-readable form works best.

### Recommended

| Style | Example |
|---|---|
| Proper case, with spaces | `Acme Corp` |
| Hyphenated suffix only when needed for disambiguation | `Acme Corp — EU` |
| Trading name over legal name where it differs | `Acme` rather than `Acme Holdings Ltd.` |

### Avoid

- Kebab-case slugs as the display name (`acme-corp`). The slug is generated automatically; using kebab-case for the display name results in a slug like `acme-corp` from `acme-corp`, which looks fine but produces awkward report headers like "Best Practice Scan — acme-corp".
- Internal codes alone (`CUST-0042`). Codes are fine in the notes field, but a report titled "Best Practice Scan — CUST-0042" is hard to share externally.
- Markdown formatting in the name. The name is rendered as plain text in PDF reports and Markdown headers; asterisks and brackets will appear literally.

> Tip: Renaming a customer at any time is safe. Existing scans, findings, and reports continue to work because they reference the immutable UUID rather than the name.

## Security and storage

BPS treats customer-level fields and connection credentials very differently.

**Customer fields** (`name`, `contact_email`, `notes`) are stored in plain text in PostgreSQL. They are not considered secret. Do not put credentials, API keys, or PII in the notes field; use the platform connection record for tokens and a secrets manager for any other sensitive data.

**Platform connection credentials** (PATs, app passwords) are encrypted at rest using Fernet symmetric encryption before persistence. The encryption key is the `CREDENTIALS_ENCRYPTION_KEY` environment variable, which must be present on the BPS server. Rotating that key requires re-entering every connection's token, so it is a deliberate operation rather than a routine one. If a stored connection token suddenly fails decryption after a deployment, the most likely cause is that the encryption key changed between deployments — edit the connection and re-enter the PAT to fix it.

## After creating

A new customer is functional but empty. The next four pieces of setup get you to a green scan and an optional automated PR.

- **Connect a platform.** Add a GitHub, GitLab, or Azure DevOps connection. See [Connecting GitHub, GitLab, and Azure DevOps](/help/platform-connections) for the exact token scopes each provider needs and how to test the credentials.
- **Run your first scan.** Once the connection validates, click **Run scan** on the customer detail page. See [Running your first scan](/help/first-scan) for what the progress indicator means and how to read each status.
- **Read the results.** Open the scan once it completes to see category scores, severity bands, and evidence panels. See [Reading scan results](/help/scan-results).
- **Customise a scan profile (optional).** If the default 16-category coverage is too broad or too narrow for this customer, create a scan profile that toggles categories and tunes per-check thresholds. The profile is per-customer and is snapshotted into the scan record at trigger time, so changes do not retroactively alter prior runs.

You can also enable agentic remediation on the customer — that is documented separately and is not a prerequisite for scanning. New customers should run a scan or two before turning on automated PRs.

## See also

- [Glossary and concepts](/help/glossary) — what every BPS term means.
- [Connecting GitHub, GitLab, and Azure DevOps](/help/platform-connections) — the next step in setup.
- [Running your first scan](/help/first-scan) — what to expect during a scan.
- [Reading scan results](/help/scan-results) — how to interpret category scores and findings.
