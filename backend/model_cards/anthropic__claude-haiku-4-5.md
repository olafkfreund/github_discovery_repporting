---
provider: anthropic
model: claude-haiku-4-5
display_name: Claude Haiku 4.5
context_window: 200000
supports_tool_use: true
supports_structured_output: true
training_data_class: web_general
training_data_cutoff: "2025-01"
license: proprietary
refreshed_at: "2026-05-12"
---

# Claude Haiku 4.5

## Provider context

The fastest and most cost-effective model in the Claude 4 family. Haiku 4.5 is optimised for
high-throughput, low-latency tasks where the change being generated is straightforward and
deterministic. Intended for bulk scanning enrichment and simple single-file remediation tasks.

Accessed via the Anthropic API directly. Authentication uses an `ANTHROPIC_API_KEY` environment
variable.

## Known limitations

- Reasoning depth is materially lower than Sonnet and Opus; avoid for tasks requiring
  multi-file cross-referencing or policy interpretation.
- More likely to produce superficially correct but semantically incorrect remediations on ambiguous
  checks; human review is strongly recommended.
- Context window matches the rest of the Claude 4 family (200,000 tokens) but effective recall
  degrades earlier on long-context tasks than Sonnet or Opus.
- Tool-use schema enforcement is the same as other Claude 4 models; misconfigured provider
  credentials raise `ValidationError`.

## Recommended remediation domains

Best fit (simple, high-volume):
- `code_quality` (linter config additions, formatting fixes)
- `collaboration` (CODEOWNERS template generation)
- `disaster_recovery` (documentation stubs)
- `migration` (boilerplate migration config generation)
- `monitoring` (simple alert-config additions)

Use with caution:
- `secrets_mgmt` (only for `.gitignore` and trivial config changes)
- `dependencies` (only for lockfile bumps with no version-constraint reasoning)

Avoid for:
- Any multi-step compliance or audit-trail requirement
- Cross-repository policy changes

## Inputs and outputs

- Pricing (per 1M tokens at time of card refresh): $0.80 input / $4.00 output. Verify against
  the live Anthropic pricing page before relying on these figures. This is approximately 4x cheaper
  than Sonnet and 19x cheaper than Opus on input tokens.
- Max recommended tokens per single-finding remediation: 20,000.
- Context window: 200,000 tokens.
- Structured output mode: native `tool_use` schema enforcement.

## Evaluation

A formal evaluation harness against the BPS test fixture repository is tracked as a Phase 5
follow-up. This section will be populated with measured acceptance rate, regression rate, and
post-merge incident rate as that work lands. Until then, treat the per-domain recommendations
above as qualitative guidance only. Do not deploy Haiku 4.5 on regulated-industry customers
(banking, public-sector profiles) without explicit sign-off from the customer.
