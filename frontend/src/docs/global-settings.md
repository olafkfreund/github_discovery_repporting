---
slug: global-settings
title: Global settings
category: admin
order: 20
summary: The system-wide singleton row holding the global kill switch, data-residency hint, retention dials, and the default LLM connection.
audience: [admin]
last_reviewed: 2026-05-13
---

# Global settings

The Global Settings page at `/settings/global` exposes a small set of system-wide knobs that affect every customer. There is no per-environment layer above it; whatever is set here is the platform default.

## What lives in Global Settings?

The singleton row holds five fields. Each one is described below alongside the field name as it appears in `GET /api/settings`.

- `global_kill_switch_enabled` — when true, **every** agent run is blocked across **every** customer. Used to halt the platform during an incident or before a planned deploy. Engaging this does not pause already-running runs; they continue to completion under their existing budget. New runs return HTTP 403 with the message `Kill switch engaged at global layer; cannot create agent runs.`
- `default_data_residency_region` — short region tag (default `eu-west`, maximum 32 characters). Not a routing decision on its own; it is published so compliance teams can align their LLM connection picks with a documented residency policy.
- `audit_log_retention_days` — integer in days (default 180, range 30 to 3650). Controls how long agent-step rows are retained before the scheduled pruning task removes them. The longer the value, the more storage you commit to.
- `streaming_log_retention_hours` — integer in hours (default 72, range 1 to 720). Controls how long streaming-run logs are retained. Streaming logs are derivative and chiefly useful for live debugging; they are not the legal record.
- `default_llm_connection_id` — optional UUID of the fallback LLM connection. Used when a customer has no LLM connection of its own configured. Most useful for sandbox or demo customers; in production every customer should have at least one connection.

## The singleton row pattern

Global Settings is stored as one row in the `settings` table whose primary key is fixed at the all-zero-and-one UUID:

```
00000000-0000-0000-0000-000000000001
```

The service layer ensures exactly one row exists, lazily creating it with defaults if it has not yet been written (for example in a fresh test database that skipped Alembic migrations). All updates go through the same row. There is no `id` parameter on the API: `GET /api/settings` and `PUT /api/settings` both operate on the singleton.

## Updating settings

The UI sits at `/settings/global`. Fields are bound to local form state; the **Save** button issues a partial update via `PUT /api/settings` with only the changed keys, and the **Discard** button resets the form to the values returned by the most recent `GET`. A saved indicator confirms a successful write.

Because every field is optional on the update payload, you can change one knob without touching the others. The backend ignores absent fields rather than treating them as nulls.

## Default LLM connection

When a customer has not configured an LLM connection, the agent runtime falls back to the connection whose UUID is set here. This is intended for two scenarios:

1. Sandbox customers used for evaluation or demos, where you do not want to provision a per-customer connection.
2. A pooled connection shared by a tightly scoped tenancy where data residency is uniform across customers.

> Setting `default_llm_connection_id` to a UUID that does not exist is permitted at write time, but any agent run that tries to resolve through it will fail with a 404 from the LLM layer. Verify the UUID before saving.

## Why audit retention is higher than streaming-log retention

Audit-log entries (each row in `agent_steps`) carry the prompt hash, the tool name, the redacted arguments, and the cost. They are the legal record of every action the agent took. They need to outlive any short-term debugging trail by a wide margin: 180 days is a sensible default for most regulated environments and the value goes up to ten years for industries that need it.

Streaming logs, by contrast, are the line-by-line transcript captured for the live UI; they are not used for compliance attestation and are cheap to throw away once the run has ended.

## Inspecting the singleton via the API

The shape returned by `GET /api/settings` is:

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "global_kill_switch_enabled": false,
  "default_data_residency_region": "eu-west",
  "audit_log_retention_days": 180,
  "streaming_log_retention_hours": 72,
  "default_llm_connection_id": null,
  "created_at": "2026-05-13T00:00:00Z",
  "updated_at": "2026-05-13T00:00:00Z"
}
```

The `created_at` and `updated_at` timestamps are useful when reconstructing the historical state for a compliance review — they record when the row was last touched. See [Compliance & audit](/help/compliance) for the wider audit-log story.
