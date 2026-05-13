---
slug: llm-providers
title: Configuring LLM providers
category: remediation
order: 20
summary: BPS supports six LLM provider backends — Anthropic, OpenAI, AWS Bedrock, Azure OpenAI, Google Vertex AI and any OpenAI-compatible endpoint — with encrypted credentials and per-customer monthly cost caps.
audience: [admin]
last_reviewed: 2026-05-13
---

The AI summary on every scan report and the remediation agent itself both call out to an LLM. BPS centralises that configuration into `LLMConnection` rows, one or more per customer, with credentials encrypted at rest and a `is_default` flag to mark the connection used when nothing more specific applies.

## Supported providers

BPS speaks to all six providers through a uniform `LLMProvider` interface. Choose the backend per connection.

### Anthropic

Direct Anthropic API. Use this when your account has an Anthropic key and you want the simplest setup. Model picks:

- `claude-opus-4-7` — most capable, best for complex diff generation in remediation.
- `claude-sonnet-4-6` — fast and cheap, ideal for triage, classification and the executive-summary path.
- `claude-haiku-4-5-20251001` — cheapest, suited to high-volume short replies.

### OpenAI

Direct OpenAI API. Models commonly chosen:

- `gpt-4o`
- `gpt-4o-mini`
- `gpt-4.1`

### AWS Bedrock

Amazon Bedrock with SigV4 authentication. Provide the AWS region in `extra_config`. Bedrock-hosted Anthropic models follow Bedrock's own naming:

- `anthropic.claude-opus-4-7`
- `anthropic.claude-sonnet-4-6`

Use this when your organisation requires inference inside a specific AWS account or region.

### Azure OpenAI

Azure-hosted OpenAI deployments. Azure routes requests by *deployment name* rather than model name. Supply:

- An `endpoint_url` such as `https://my-tenant.openai.azure.com`.
- An API key.
- The deployment name in `extra_config.deployment` (Azure-specific).

### Google Vertex AI

Vertex AI with a service-account JSON credential. Supply the GCP project and location in `extra_config`. Suitable for organisations that already standardise on GCP.

### OpenAI-compatible

Any endpoint that speaks the OpenAI chat-completions API: LocalAI, vLLM, llama.cpp server, Ollama, or a self-hosted gateway. Set `endpoint_url` to your service base URL. The cost cap will record `$0.00` per run because BPS has no pricing table for self-hosted models — useful for free internal inference.

## Adding a connection

Connections are managed at `/settings/llm-providers?customer_id=<id>`. The page lists existing connections and offers a **New connection** form. Required fields:

- **Name** — human-readable label, unique within the customer.
- **Provider** — one of the six listed above.
- **Model** — provider-specific identifier (the form shows examples).
- **API key** — encrypted with Fernet before persistence; the plaintext never touches the database.
- **Endpoint URL** — optional override (Azure, OpenAI-compatible).
- **Extra config** — JSON for provider-specific knobs (AWS region, GCP project, Azure deployment name).
- **Is default** — when true, this connection becomes the customer's default and the previous default is automatically unset.

Use **Test connection** before saving. The endpoint runs a one-token roundtrip against the provider, returning latency and the model's reply so credentials and reachability are verified before any scan or agent run depends on them.

## Choosing a model

A practical rubric:

- **Opus-class models** (Anthropic Opus, GPT-4o full, Vertex Gemini Pro) — use when the agent is generating non-trivial diffs across multiple files, or when the executive summary needs nuance for a high-visibility customer.
- **Sonnet-class models** (Anthropic Sonnet, GPT-4o-mini) — use for triage, short replies and most remediation tasks. Substantially cheaper.
- **Haiku-class models** (Anthropic Haiku, smaller Vertex/OpenAI variants) — use for cheap classification or batched short tasks where latency matters more than nuance.

Per-token pricing varies by provider. BPS records `total_input_tokens`, `total_output_tokens` and `total_cost_usd` on every `AgentRun` so you can correlate spend with model choice over time.

> Tip: A common configuration is one Opus connection (for remediation) marked default, and a separate Sonnet connection for AI summaries. Service code picks the right one at the right moment.

## Cost caps

Every customer has a `RemediationPolicy.max_cost_usd_per_month` (default `$100.00`). `cost_cap_service.check()` sums `AgentRun.total_cost_usd` across all of the customer's scans since the first day of the current calendar month in UTC and compares it to the cap.

The result is exposed at `GET /api/customers/{id}/cost-status` so the frontend can render a monthly spend bar at the top of the remediation page (Phase 4). When the spend equals or exceeds the cap, `agent_service.create_agent_run` hard-rejects new runs with HTTP 409 and a clear error. Existing runs already in `running` are not interrupted by the cap — only newly created runs are gated.

Cost caps do not apply to the AI summary path on scan reports; only to the agent. The summary path is metered but uncapped (it costs a few cents per scan even on the priciest model).

## Default LLM connection

Global Settings exposes a `default_llm_connection_id` field on the singleton `Setting` row. It refers to any `LLMConnection` and acts as the fallback used when a customer has no default connection of their own.

The lookup order is therefore:

1. Customer's `LLMConnection.is_default == true`.
2. Global `Setting.default_llm_connection_id`.
3. No fallback — the operation fails clean with a clear error.

Setting a global default is recommended in multi-tenant deployments where new customers should be able to scan and read AI summaries without per-customer onboarding overhead.

## Worked example

A connection record for AWS Bedrock with the Anthropic Opus model. Note that `api_key_encrypted` is shown here as `null` because Bedrock authentication is done via AWS credentials (IAM role on the BPS host), not an explicit key.

```json
{
  "name": "Bedrock Opus (eu-west-1)",
  "provider": "bedrock",
  "model": "anthropic.claude-opus-4-7",
  "endpoint_url": null,
  "api_key_encrypted": null,
  "extra_config": {
    "aws_region": "eu-west-1",
    "aws_profile": "bps-bedrock"
  },
  "is_default": true
}
```

For an Anthropic direct-API connection the shape is simpler:

```json
{
  "name": "Anthropic Sonnet",
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "endpoint_url": null,
  "extra_config": null,
  "is_default": false
}
```

(The API key is supplied through the form and encrypted server-side; it never appears in the JSON the UI displays back.)

## Next steps

- [Remediation policy and cost caps](/help/remediation-policy) — set the monthly cap.
- [Agentic remediation overview](/help/remediation-overview) — see how the connection feeds the runner.
- [Global settings](/help/global-settings) — pick the global fallback connection.
