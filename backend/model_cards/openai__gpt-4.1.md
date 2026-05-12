---
provider: openai
model: gpt-4.1
display_name: GPT-4.1
context_window: 1000000
supports_tool_use: true
supports_structured_output: true
training_data_class: web_general
training_data_cutoff: "2025-06"
license: proprietary
refreshed_at: "2026-05-12"
---

# GPT-4.1

## Provider context

Released by OpenAI in early 2025. GPT-4.1 succeeds the GPT-4o line with a significantly larger
context window (1,000,000 tokens) and improved instruction following, making it the most capable
OpenAI model available for long-context remediation tasks. It is positioned as a direct competitor
to Claude Opus 4.7 for complex, multi-file remediation workflows.

Accessed via the OpenAI API (`api.openai.com`). Authentication uses an `OPENAI_API_KEY`
environment variable. Configure the LLM connection with `provider=openai` and `model=gpt-4.1`.

## Known limitations

- The BPS `LoopCaps` setting caps context at 200,000 tokens per run regardless of the model's
  native window; the full 1M window is not exploited in the current harness.
- Structured output via `response_format={"type": "json_schema"}` is supported and more reliable
  than earlier GPT-4 variants, but still handled differently from Anthropic's `tool_use`; the
  LiteLLM adapter normalises the difference.
- Per-token pricing is materially higher than GPT-4o; evaluate cost-per-finding before deploying
  at scale.
- Rate limits on the default API tier may be lower than GPT-4o for concurrent requests.

## Recommended remediation domains

Best fit:
- `cicd` (complex multi-job workflow synthesis)
- `repo_governance` (cross-repository policy documents)
- `compliance` (multi-step audit-aligned changes)
- `sdlc_process` (release-process documentation)
- `secrets_mgmt` (complex vault integration patterns)

Acceptable:
- All other domains where GPT-4o is currently recommended

Avoid for high-volume bulk tasks; prefer GPT-4o Mini or Claude Haiku on those workloads.

## Inputs and outputs

- Pricing (per 1M tokens at time of card refresh): $2.00 input / $8.00 output. Verify against
  the live OpenAI pricing page (`platform.openai.com/pricing`) before relying on these figures.
- Max recommended tokens per single-finding remediation: 50,000 (the BPS harness caps runs at
  200k via `LoopCaps`).
- Context window: 1,000,000 tokens native; 200,000 tokens effective within BPS.
- Structured output mode: `response_format={"type": "json_schema"}` via the OpenAI API;
  managed transparently by the BPS LiteLLM adapter.

## Evaluation

A formal evaluation harness against the BPS test fixture repository is tracked as a Phase 5
follow-up. This section will be populated with measured acceptance rate, regression rate, and
post-merge incident rate as that work lands. Until then, treat the per-domain recommendations
above as qualitative guidance.
