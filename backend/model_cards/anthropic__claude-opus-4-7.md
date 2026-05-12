---
provider: anthropic
model: claude-opus-4-7
display_name: Claude Opus 4.7
context_window: 200000
supports_tool_use: true
supports_structured_output: true
training_data_class: web_general
training_data_cutoff: "2025-09"
license: proprietary
refreshed_at: "2026-05-12"
---

# Claude Opus 4.7

## Provider context

Released by Anthropic in early 2026. Opus is the flagship general-purpose model in the Claude 4
family, tuned for long-form reasoning and tool-use workflows. Recommended for complex remediation
tasks across the full 16-scanner domain matrix.

Accessed via the Anthropic API directly. Authentication uses an `ANTHROPIC_API_KEY` environment
variable. No additional infrastructure configuration is required.

## Known limitations

- Long-context retrieval can hallucinate filenames when workspace size exceeds the model's effective
  recall (empirically degrades past approximately 150,000 tokens in the remediation harness).
- Tool-use schema enforcement is strict; provider misconfigurations surface as `ValidationError`
  rather than free-form retry.
- Refuses without clear justification on prompts that resemble red-team scenarios; for
  security-sensitive remediation use the recommended per-check operator prompts from the standard
  or banking agent profile.
- Throughput is lower than Sonnet and Haiku; unsuitable for bulk low-complexity findings where
  cost-per-finding matters more than reasoning depth.

## Recommended remediation domains

Best fit:
- `repo_governance` (CODEOWNERS synthesis, branch-protection policy)
- `cicd` (complex workflow synthesis, multi-job dependency graphs)
- `compliance` (multi-step audit-aligned changes requiring chain-of-thought)
- `sdlc_process` (release-process documentation and policy generation)

Acceptable but sub-optimal:
- `identity_access`, `secrets_mgmt`, `dependencies`

Avoid for high-volume, simple tasks where `claude-haiku-4-5` delivers the same acceptance rate at
a fraction of the cost.

## Inputs and outputs

- Pricing (per 1M tokens at time of card refresh): $15.00 input / $75.00 output. Verify against
  the live Anthropic pricing page before relying on these figures.
- Max recommended tokens per single-finding remediation: 50,000.
- Context window: 200,000 tokens. The BPS runner caps per-run usage at 200,000 tokens via
  `LoopCaps` regardless of model.
- Structured output mode: uses Anthropic's native `tool_use` schema enforcement.

## Evaluation

A formal evaluation harness against the BPS test fixture repository is tracked as a Phase 5
follow-up. This section will be populated with measured acceptance rate, regression rate, and
post-merge incident rate as that work lands. Until then, treat the per-domain recommendations
above as qualitative guidance based on developer experience during Phase 4 integration testing.
