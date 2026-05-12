---
provider: vertex
model: gemini-2-0-flash
display_name: Gemini 2.0 Flash (Vertex AI)
context_window: 1000000
supports_tool_use: true
supports_structured_output: true
training_data_class: web_general
training_data_cutoff: "2025-01"
license: proprietary
refreshed_at: "2026-05-12"
---

# Gemini 2.0 Flash (Vertex AI)

## Provider context

Google's Gemini 2.0 Flash model, accessed via the Vertex AI API on Google Cloud Platform. Flash
is positioned as a cost-effective, high-throughput model within the Gemini 2.0 family, with a
very large native context window (1,000,000 tokens) and competitive latency. It is an alternative
to Claude Haiku and GPT-4o Mini for high-volume remediation tasks on teams with existing GCP
infrastructure.

Authentication uses GCP service account credentials or Application Default Credentials (ADC).
The BPS LLM connection must be configured with:
- `provider=vertex`
- `model=gemini-2-0-flash`
- `GOOGLE_CLOUD_PROJECT` environment variable set to the GCP project ID.
- `GOOGLE_CLOUD_REGION` set to the Vertex AI region (e.g. `us-central1`).
- Either a service account key file (via `GOOGLE_APPLICATION_CREDENTIALS`) or ADC via
  `gcloud auth application-default login`.

No OpenAI or Anthropic credentials are required.

## Known limitations

- Structured output is implemented via Gemini's JSON schema mode (`response_mime_type` +
  `response_schema` in the Vertex API). The BPS LiteLLM adapter handles normalisation, but
  deeply nested schemas may behave differently from Anthropic's `tool_use` or OpenAI's
  `json_schema` mode.
- The 1M token native window is not fully exploited by the BPS harness, which caps runs at
  200,000 tokens via `LoopCaps`.
- Regional availability and quota limits are managed in the GCP console; default quotas for new
  projects are low. Request increases before running large-org scans.
- Gemini's function-calling schema has different constraints from the OpenAI and Anthropic schemas
  on optional fields and recursive references; the LiteLLM adapter abstracts most differences but
  edge cases may surface.
- Pricing is managed by Google Cloud; use the GCP pricing calculator for accurate cost estimates.

## Recommended remediation domains

Best fit (high-volume, cost-sensitive):
- `code_quality`, `collaboration`, `monitoring`, `migration`
- `dependencies` (for simple lockfile and constraint bumps)

Acceptable:
- `cicd` (standard workflow fixes), `container_security` (Dockerfile additions)

Use with caution for:
- Complex multi-step compliance tasks
- Any domain requiring strict chain-of-thought auditing

Avoid for regulated-industry customers without additional evaluation against the BPS test fixture.

## Inputs and outputs

- Pricing: set by Google Cloud; check the Vertex AI pricing page for current on-demand rates.
  Gemini 2.0 Flash is typically priced below equivalent throughput models from Anthropic and
  OpenAI. Do not rely on figures from third-party sources.
- Max recommended tokens per single-finding remediation: 20,000 (conservative, pending harness
  evaluation).
- Context window: 1,000,000 tokens native; 200,000 tokens effective within BPS.
- Structured output mode: Gemini JSON schema mode via the Vertex AI API, normalised by the
  BPS LiteLLM adapter.

## Evaluation

A formal evaluation harness against the BPS test fixture repository is tracked as a Phase 5
follow-up. This section will be populated with measured acceptance rate, regression rate, and
post-merge incident rate as that work lands. Gemini 2.0 Flash has not yet been run against the
full BPS scanner domain matrix; treat all per-domain recommendations as provisional.
