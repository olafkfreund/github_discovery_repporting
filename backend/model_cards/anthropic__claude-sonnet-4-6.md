---
provider: anthropic
model: claude-sonnet-4-6
display_name: Claude Sonnet 4.6
context_window: 200000
supports_tool_use: true
supports_structured_output: true
training_data_class: web_general
training_data_cutoff: "2025-04"
license: proprietary
refreshed_at: "2026-05-12"
---

# Claude Sonnet 4.6

## Provider context

Released by Anthropic in mid-2025. Sonnet 4.6 sits between Haiku and Opus in the Claude 4 family,
offering a practical balance of reasoning quality, throughput, and cost. It is the primary model
used by the BPS analysis engine for structured-output report generation.

Accessed via the Anthropic API directly. Authentication uses an `ANTHROPIC_API_KEY` environment
variable.

## Known limitations

- Reasoning depth on multi-file, multi-step remediations is lower than Opus 4.7; complex
  cross-repository policy changes may require prompt decomposition.
- Still enforces strict tool-use schema validation; provider misconfigurations raise
  `ValidationError`.
- Context window is the same as Opus (200,000 tokens), but effective recall at very long contexts
  has not been independently validated in the BPS harness.

## Recommended remediation domains

Best fit:
- `cicd` (standard workflow fixes, action pinning)
- `secrets_mgmt` (`.gitignore` additions, secret-scanner config)
- `dependencies` (lockfile updates, version constraint bumps)
- `sast` (tool-config generation, scan-integration patches)
- `container_security` (Dockerfile linting fixes)

Acceptable:
- `repo_governance`, `code_quality`, `monitoring`

Avoid for very complex multi-step compliance tasks; prefer Opus 4.7 for those.

## Inputs and outputs

- Pricing (per 1M tokens at time of card refresh): $3.00 input / $15.00 output. Verify against
  the live Anthropic pricing page before relying on these figures.
- Max recommended tokens per single-finding remediation: 40,000.
- Context window: 200,000 tokens.
- Structured output mode: native `tool_use` schema enforcement.

## Evaluation

A formal evaluation harness against the BPS test fixture repository is tracked as a Phase 5
follow-up. This section will be populated with measured acceptance rate, regression rate, and
post-merge incident rate as that work lands. Sonnet 4.6 is the current default model for BPS
analysis; operational experience from Phase 4 indicates consistent structured-output adherence
across all 16 scanner domains.
