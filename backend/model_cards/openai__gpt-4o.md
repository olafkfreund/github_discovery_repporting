---
provider: openai
model: gpt-4o
display_name: GPT-4o
context_window: 128000
supports_tool_use: true
supports_structured_output: true
training_data_class: web_general
training_data_cutoff: "2024-10"
license: proprietary
refreshed_at: "2026-05-12"
---

# GPT-4o

## Provider context

OpenAI's flagship multimodal model as of late 2024. GPT-4o ("o" for omni) supports text, image,
and audio modalities; the BPS remediation harness uses text and tool-use modes only. It is a
strong general-purpose alternative when the Anthropic API is unavailable or when customers have
an existing OpenAI contract.

Accessed via the OpenAI API (`api.openai.com`). Authentication uses an `OPENAI_API_KEY`
environment variable. Configure the LLM connection with `provider=openai` and `model=gpt-4o`.

## Known limitations

- Context window is 128,000 tokens, half that of Claude 4 models. Large repositories with many
  findings may require more aggressive context chunking in the remediation harness.
- Structured output is implemented via `response_format={"type": "json_schema", "json_schema": ...}`
  rather than Anthropic-style `tool_use`; the BPS LiteLLM adapter handles this transparently, but
  edge cases in deeply-nested schemas may behave differently.
- Rate limits on the default OpenAI tier are stricter than Anthropic for concurrent requests;
  expect throttling on large-org scans.
- Function calling is reliable but occasionally over-generates arguments on under-specified schemas.

## Recommended remediation domains

Best fit:
- `cicd` (GitHub Actions workflow synthesis)
- `repo_governance` (branch-protection policy patches)
- `sast` (tool-config generation for GitHub Advanced Security)
- `container_security` (Dockerfile and Compose fixes)

Acceptable:
- `dependencies`, `secrets_mgmt`, `code_quality`

Use with caution for compliance-heavy domains where strict chain-of-thought auditing is required;
Anthropic's models have more predictable refusal behaviour on ambiguous prompts.

## Inputs and outputs

- Pricing (per 1M tokens at time of card refresh): $2.50 input / $10.00 output. Verify against
  the live OpenAI pricing page (`platform.openai.com/pricing`) before relying on these figures.
- Max recommended tokens per single-finding remediation: 30,000 (leaving headroom for
  system context and tool schemas within the 128k window).
- Context window: 128,000 tokens.
- Structured output mode: `response_format={"type": "json_schema"}` via the OpenAI API;
  managed transparently by the BPS LiteLLM adapter.

## Evaluation

A formal evaluation harness against the BPS test fixture repository is tracked as a Phase 5
follow-up. This section will be populated with measured acceptance rate, regression rate, and
post-merge incident rate as that work lands. Until then, treat the per-domain recommendations
above as qualitative guidance.
