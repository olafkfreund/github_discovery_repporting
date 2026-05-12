---
provider: openai
model: gpt-4o-mini
display_name: GPT-4o Mini
context_window: 128000
supports_tool_use: true
supports_structured_output: true
training_data_class: web_general
training_data_cutoff: "2024-07"
license: proprietary
refreshed_at: "2026-05-12"
---

# GPT-4o Mini

## Provider context

A cost-optimised variant of GPT-4o, released by OpenAI in mid-2024. GPT-4o Mini trades reasoning
depth for significantly lower per-token cost and higher throughput. It is the OpenAI equivalent of
Claude Haiku: suitable for high-volume, low-complexity remediation tasks where cost-per-finding
is the primary constraint.

Accessed via the OpenAI API (`api.openai.com`). Authentication uses an `OPENAI_API_KEY`
environment variable. Configure the LLM connection with `provider=openai` and `model=gpt-4o-mini`.

## Known limitations

- Reasoning quality on multi-step or policy-interpretation tasks is substantially below GPT-4o
  and Claude Sonnet; inappropriate for compliance or audit-trail remediations.
- Same 128,000-token context window as GPT-4o; the same chunking constraints apply.
- Structured output via `response_format={"type": "json_schema"}` is supported but schema
  adherence is less reliable on deeply nested structures than GPT-4o.
- Human review of every generated patch is strongly recommended; acceptance-rate data is
  not yet available from the BPS evaluation harness.

## Recommended remediation domains

Best fit (simple, high-volume):
- `code_quality` (linter config additions)
- `collaboration` (CODEOWNERS template stubs)
- `monitoring` (alert-config boilerplate)
- `migration` (migration-config generation)

Use with caution:
- `secrets_mgmt`, `dependencies` (only trivial single-file changes)

Avoid:
- All compliance, audit, and multi-step policy remediations
- Any finding requiring cross-file reasoning

## Inputs and outputs

- Pricing (per 1M tokens at time of card refresh): $0.15 input / $0.60 output. Verify against
  the live OpenAI pricing page (`platform.openai.com/pricing`) before relying on these figures.
  This is approximately 17x cheaper than GPT-4o on input tokens.
- Max recommended tokens per single-finding remediation: 15,000.
- Context window: 128,000 tokens.
- Structured output mode: `response_format={"type": "json_schema"}` via the OpenAI API;
  managed transparently by the BPS LiteLLM adapter.

## Evaluation

A formal evaluation harness against the BPS test fixture repository is tracked as a Phase 5
follow-up. Until then, treat the per-domain recommendations above as qualitative guidance only.
Do not deploy GPT-4o Mini on regulated-industry customers without explicit sign-off.
