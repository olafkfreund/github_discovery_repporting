---
slug: api-reference
title: API reference
category: reference
order: 10
summary: Directory of REST endpoints exposed by the BPS backend, grouped by resource. Use this as a quick lookup; see docs/api-reference.md in the repo for parameter detail.
audience: [admin]
last_reviewed: 2026-05-13
---

# API reference

BPS exposes a REST API at `http://<host>/api`. This page is a quick directory of the endpoints grouped by resource, with the HTTP method, path, and a one-line summary. For full request and response schemas, see `docs/api-reference.md` in the repository or the OpenAPI schema served at `/docs` and `/openapi.json` by the FastAPI app.

> All paths in the tables below are listed without the leading `/api` prefix.

## Customers

| Method | Path | Purpose |
|---|---|---|
| GET | `/customers/` | List every customer |
| POST | `/customers/` | Create a new customer |
| GET | `/customers/{customer_id}` | Get one customer |
| PUT | `/customers/{customer_id}` | Update a customer |
| DELETE | `/customers/{customer_id}` | Delete a customer |

## Connections

| Method | Path | Purpose |
|---|---|---|
| GET | `/customers/{customer_id}/connections` | List a customer's platform connections |
| POST | `/customers/{customer_id}/connections` | Add a platform connection |
| PUT | `/connections/{connection_id}` | Update a connection |
| DELETE | `/connections/{connection_id}` | Delete a connection |
| POST | `/connections/{connection_id}/validate` | Test the connection credentials |
| PUT | `/connections/{connection_id}/skills-override` | Set the per-connection skill override map |

## Scans

| Method | Path | Purpose |
|---|---|---|
| POST | `/customers/{customer_id}/scans` | Trigger a new scan |
| GET | `/customers/{customer_id}/scans` | List a customer's scans |
| GET | `/scans/{scan_id}` | Get one scan |
| GET | `/scans/{scan_id}/findings` | List findings for a scan |
| GET | `/scans/{scan_id}/scores` | List category scores for a scan |

## Scan profiles

| Method | Path | Purpose |
|---|---|---|
| GET | `/scanners/registry` | Full scanner registry (categories, checks, threshold defaults) |
| GET | `/customers/{customer_id}/scan-profiles` | List scan profiles for a customer |
| POST | `/customers/{customer_id}/scan-profiles` | Create a scan profile |
| GET | `/scan-profiles/{profile_id}` | Get one scan profile |
| PUT | `/scan-profiles/{profile_id}` | Update a scan profile |
| DELETE | `/scan-profiles/{profile_id}` | Delete a scan profile |

## Reports

| Method | Path | Purpose |
|---|---|---|
| POST | `/scans/{scan_id}/reports` | Generate a report for a scan |
| GET | `/customers/{customer_id}/reports` | List reports for a customer |
| GET | `/reports/{report_id}` | Get one report |
| GET | `/reports/{report_id}/download` | Download the PDF report |
| GET | `/reports/{report_id}/download/excel` | Download the Excel workbook |
| GET | `/reports/{report_id}/download/zip` | Download the Markdown + Excel bundle |

## LLM connections

| Method | Path | Purpose |
|---|---|---|
| GET | `/llm-connections/` | List LLM connections (filterable by `customer_id`) |
| POST | `/llm-connections/` | Create an LLM connection |
| GET | `/llm-connections/{connection_id}` | Get one LLM connection |
| PUT | `/llm-connections/{connection_id}` | Update an LLM connection |
| DELETE | `/llm-connections/{connection_id}` | Delete an LLM connection |
| POST | `/llm-connections/validate` | Validate a candidate payload before save |
| POST | `/llm-connections/{connection_id}/test` | Test an existing connection |

## Remediation policy

| Method | Path | Purpose |
|---|---|---|
| GET | `/customers/{customer_id}/remediation-policy` | Get the customer remediation policy |
| PUT | `/customers/{customer_id}/remediation-policy` | Upsert the customer remediation policy |
| DELETE | `/customers/{customer_id}/remediation-policy` | Delete the customer remediation policy |

## Cost status

| Method | Path | Purpose |
|---|---|---|
| GET | `/customers/{customer_id}/cost-status` | Current month spend vs cap for a customer |

## Agent instructions and profiles

| Method | Path | Purpose |
|---|---|---|
| GET | `/customers/{customer_id}/agent-instructions` | Get customer AGENTS.md content |
| PUT | `/customers/{customer_id}/agent-instructions` | Upsert customer AGENTS.md content |
| DELETE | `/customers/{customer_id}/agent-instructions` | Delete customer AGENTS.md content |
| GET | `/agent-profiles/` | List built-in AGENTS.md profiles |
| GET | `/agent-profiles/{slug}/content` | Get one profile body |

## Skills

| Method | Path | Purpose |
|---|---|---|
| GET | `/customers/{customer_id}/skills` | List effective skills for a customer |
| POST | `/customers/{customer_id}/skills` | Create a custom skill |
| PUT | `/customers/{customer_id}/skills/{name}` | Update a skill (or toggle a built-in) |
| DELETE | `/customers/{customer_id}/skills/{name}` | Delete a custom skill |
| GET | `/skills/{name}/content` | Get the effective body for a skill |
| GET | `/skills-registry` | List the built-in skill catalogue |
| GET | `/skills-registry/{name}/content` | Get a built-in skill body |

## Agent runs

| Method | Path | Purpose |
|---|---|---|
| POST | `/scans/{scan_id}/agent-runs` | Trigger an agent run |
| GET | `/agent-runs` | List agent runs (filterable by `scan_id`, `customer_id`, `status`, `since`) |
| GET | `/agent-runs/estimate` | Cost estimate for a candidate run |
| GET | `/agent-runs/{id}` | Get one agent run with steps |
| POST | `/agent-runs/{id}/cancel` | Request cancellation of a running run |
| POST | `/agent-runs/{id}/events` | Receive CI-mode step events (HMAC-signed) |
| GET | `/agent-runs/{id}/stream` | Server-sent events stream of agent steps |

## Global settings

| Method | Path | Purpose |
|---|---|---|
| GET | `/settings` | Get the global settings singleton |
| PUT | `/settings` | Partially update the global settings singleton |

## Authentication

BPS does not require authentication today. The platform is intended for deployment inside a customer network, behind an existing identity-aware proxy. An authentication subsystem (OIDC plus role-based access control) is on the product roadmap and will be added once the first customer requires it.

## Error shapes

Errors follow FastAPI conventions:

- For 4xx errors raised by routers, the body is `{"detail": "<human-readable message>"}`.
- For 422 validation errors, the body is `{"detail": [{"loc": [...], "msg": "...", "type": "..."}, ...]}` where each item describes one failed field. The frontend client joins the `msg` strings with semicolons for display.
- For 5xx errors the body is `{"detail": "Internal Server Error"}`; the real error is in the backend logs.

The frontend `request` helper in `frontend/src/api/client.ts` parses both shapes and throws an `Error` with a flattened message string.
