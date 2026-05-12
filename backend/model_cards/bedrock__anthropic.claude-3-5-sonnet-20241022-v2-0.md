---
provider: bedrock
model: anthropic.claude-3-5-sonnet-20241022-v2-0
display_name: Claude 3.5 Sonnet v2 (Bedrock)
context_window: 200000
supports_tool_use: true
supports_structured_output: true
training_data_class: web_general
training_data_cutoff: "2024-04"
license: proprietary
refreshed_at: "2026-05-12"
---

# Claude 3.5 Sonnet v2 (Bedrock)

## Provider context

The Anthropic Claude 3.5 Sonnet v2 model hosted on AWS Bedrock. The underlying model is
identical to Anthropic's direct offering, but it is accessed via AWS infrastructure, which means
pricing, latency, and quota management are governed by the AWS Bedrock console rather than
Anthropic's API portal. This variant is appropriate for organisations that require all AI traffic
to remain within AWS, or that have existing AWS enterprise agreements covering Bedrock usage.

Authentication uses IAM credentials rather than an API key. The BPS LLM connection must be
configured with:
- `provider=bedrock`
- `model=anthropic.claude-3-5-sonnet-20241022-v2-0`
- An IAM role or access key pair with `bedrock:InvokeModel` permission on the target model ARN.
- `AWS_REGION` must be set to a region where the model is available (e.g. `us-east-1`,
  `eu-west-1`); check the AWS Bedrock console for regional availability.

No `ANTHROPIC_API_KEY` is required or used. Credentials are managed via the standard AWS
credential chain (`~/.aws/credentials`, environment variables, or instance profile).

## Known limitations

- Regional availability is limited compared to direct Anthropic API access; not all AWS regions
  host Claude 3.5 Sonnet v2. Verify availability in the target region before deployment.
- Bedrock API throttling limits are configured per-AWS account and per-region; defaults are lower
  than Anthropic's API limits for most commercial accounts. Request limit increases via the AWS
  console before running large-org scans.
- Pricing is set by AWS Bedrock, not Anthropic; the figures differ from Anthropic's direct API.
  Verify current pricing in the AWS Bedrock console under Model pricing.
- Cross-account or cross-region invocations may require additional IAM trust policies.
- Model version is pinned to `20241022-v2`; Bedrock does not automatically roll forward to newer
  Claude 3.5 Sonnet versions. A card update and model-ID change will be required when upgrading.

## Recommended remediation domains

This model is functionally equivalent to Claude 3.5 Sonnet accessed directly, so domain
recommendations mirror the Sonnet tier:

Best fit:
- `cicd`, `secrets_mgmt`, `dependencies`, `sast`, `container_security`

Acceptable:
- `repo_governance`, `code_quality`, `monitoring`

Avoid for very complex multi-step compliance tasks; prefer a Claude Opus-tier model for those.

## Inputs and outputs

- Pricing: set by AWS Bedrock; check the AWS Bedrock console for current on-demand and provisioned
  throughput rates. Do not rely on Anthropic's direct API pricing for this configuration.
- Max recommended tokens per single-finding remediation: 40,000.
- Context window: 200,000 tokens.
- Structured output mode: native Anthropic `tool_use` schema enforcement, proxied through
  the Bedrock `InvokeModel` API.

## Evaluation

A formal evaluation harness against the BPS test fixture repository is tracked as a Phase 5
follow-up. This section will be populated with measured acceptance rate, regression rate, and
post-merge incident rate as that work lands. Until then, treat the per-domain recommendations
above as qualitative guidance.
