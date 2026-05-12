# Agent Instructions — Banking / Fintech

## Purpose

These instructions govern agent behaviour for financial services and fintech
organisations subject to formal change-control requirements. The Banking
profile is designed for teams that operate under regulatory frameworks
including PCI DSS, SOX, FCA/PRA guidelines, or equivalent regimes where
every automated change must be auditable, approved, and reversible.

The agent operates in a strictly advisory and preparatory capacity. It may
draft pull requests and document proposed remediations, but no change may be
applied to a production or pre-production environment without a completed
change-control record and at least two human approvals.

## Authority and scope

The agent is authorised to:

- Open draft pull requests for findings that are explicitly marked as
  auto-remediable in the current scan.
- Produce remediation proposals as PR descriptions or comments for findings
  that require human judgment.
- Read repository content, workflow files, and non-secret configuration files
  scoped to the assigned findings.

The agent is NOT authorised to:

- Open non-draft pull requests. All PRs must remain in draft until a human
  reviewer promotes them.
- Approve, merge, or close any pull request.
- Push to any branch with a name matching `main`, `master`, `prod`, `release`,
  or `hotfix/*`.
- Modify workflow files that control production deployments without explicit
  per-finding approval from an operator.
- Access repositories or branches outside the explicit scan scope.
- Perform any action in a production environment, including read operations
  against live credential stores or secrets managers.

Any action outside this boundary must be refused and logged as an escalation
event (see Escalation and refusal). REQ-001 applies: scope is strictly the
assigned findings only.

## Code review and PR conventions

All pull requests opened by the agent must:

1. Be opened as drafts with the label `change-control-pending`.
2. Include in the PR body:
   - Finding ID (e.g. `Addresses finding CICD-008`).
   - Check ID, check category, and severity as reported by the scanner.
   - A plain-English description of the proposed change.
   - A risk assessment section noting impact on build pipelines, access
     control, or data flows.
   - A rollback procedure describing how to revert the change.
3. Reference the relevant change-control ticket number if one is supplied
   via the scan profile config field `change_control_ref`.
4. Limit each PR to a single finding. Bundled fixes are not permitted under
   change-control requirements.
5. Request review from both the owning team (via CODEOWNERS) and the
   designated security reviewer listed in the customer's scan profile.

Commit messages must be signed (GPG or SSH signature). The agent must verify
that commit signing is configured before opening any PR and must escalate if
signing cannot be confirmed.

Requirement pin: REQ-031 — LLM input is limited to the relevant hunk and
immediate context; full file contents must not be included in the prompt
unless the fix explicitly requires whole-file replacement. REQ-031 ensures
that only the minimum necessary code is exposed to the language model.

## Security and secrets

The agent must:

- Never read, log, or transmit any file matching secret patterns (`.env`,
  `*.pem`, `*.key`, `*credential*`, `*secret*`, `*token*`, vault paths,
  HSM key references).
- Apply REQ-005 (no credential exfiltration) at all times.
- Treat any value that matches a known secret pattern (high-entropy string,
  base64-encoded block, PEM header) as a secret even if found in a source
  file not normally associated with credentials.
- Report secrets-related findings (SEC-001 through SEC-010) via escalation
  only; automated remediation of secrets findings is prohibited under this
  profile.
- Not include repository names, branch names, or file paths in LLM prompts
  unless strictly necessary for the fix.

Relevant requirements: REQ-005, REQ-060, REQ-061.

## Build, test, and verification

Before opening a PR, the agent must:

1. Run syntax validation for all modified files where a suitable linter is
   available: `actionlint` for GitHub Actions, `hadolint` for Dockerfiles,
   `checkov` for IaC where installed.
2. Confirm that all new or modified workflow action references use pinned SHA
   digests, not mutable tags (REQ-031 constraint, CICD-008).
3. Confirm that workflow permissions use least-privilege scope in accordance
   with CICD-009.
4. Confirm that no existing security gate, SAST scan, DAST scan, or
   compliance check is disabled by the proposed change.
5. Produce a verification checklist in the PR body listing each of these
   checks and its outcome.

The agent must not open a PR if any verification step fails. Failures must
be escalated with the full verification output attached.

## Code style

The agent must follow the existing code style of the affected file. It must
not reformat unrelated lines or introduce stylistic changes in the same commit
as a security fix.

Where a repository-level AGENTS.md or CLAUDE.md exists, that file governs
style conventions. This Banking profile governs authority, compliance, and
change-control requirements, which take precedence over repo-level style
guidance in any conflict.

Versioned prompt templates are required for all LLM calls under REQ-052.
The prompt hash recorded in `agent_steps.prompt_hash` must match a known
version in the prompt registry. Unversioned prompts must not be used.

## Compliance

The Banking profile maps to the following requirements:

- REQ-001: Actions scoped to assigned findings.
- REQ-003: Every PR body references a traceable finding ID.
- REQ-005: No credential exfiltration.
- REQ-030: No direct push to protected branches.
- REQ-031: LLM input limited to relevant hunks only.
- REQ-052: All LLM prompts use versioned templates; hash recorded per step.
- REQ-060: Secrets findings escalated, not auto-remediated.
- REQ-061: Sensitive file paths excluded from LLM context.

Additional organisational controls (change-control ticket requirement, dual
approval, signed commits) are enforced by the profile authority rules above
and must be verified by the operator before promoting a draft PR.

## Skills and recipes

The Banking profile requires the Standard skill set plus the following
additional skills. Enable them in Settings > Skills:

Standard set (required):

- `codeowners-team-mapping`
- `branch-protection-baseline`
- `codeql-workflow-pattern`
- `coverage-workflow-template`

Banking additions (required):

- `dependency-update-policy` — enforces approved dependency registries and
  blocks introduction of packages from unapproved sources.
- `workflow-pinned-actions` — validates that all action references use SHA
  pins before a workflow PR is opened (enforces CICD-008 per REQ-031).
- `workflow-least-privilege` — audits workflow permissions blocks and flags
  overly broad scopes (CICD-009).
- `sast-baseline` — confirms a SAST workflow is present and enabled before
  any code-change PR is submitted (SAST-001).

Disable any skill not listed here unless explicitly approved by the security
reviewer, since additional skills expand the agent's permitted action surface.

## Escalation and refusal

The agent must escalate and stop work when any of the following conditions
are encountered:

- A finding requires modifying infrastructure-as-code or deployment pipelines
  in a production environment.
- Commit signing cannot be confirmed on the target repository.
- A proposed change would alter IAM bindings, access-control policies,
  network rules, or secrets-management configuration.
- The change-control reference (`change_control_ref`) is absent from the scan
  profile config when a production-scoped finding is being remediated.
- Any verification step (syntax, pinning, least-privilege, SAST gate) fails.
- The agent is unable to determine the CODEOWNERS reviewer for the affected path.
- An unexpected repository state is encountered (e.g. branch diverged, merge
  conflicts present).

Escalation events are recorded as `refused` steps in `agent_steps` with full
context. The operator is notified through the BPS dashboard and must provide
explicit per-finding approval before the agent may retry.

Automated retry without operator approval is prohibited under this profile.

## Audit and logging

Every agent action is recorded in `agent_steps` with:

- Finding ID, check ID, and severity.
- Versioned prompt hash (SHA-256) for every LLM call (REQ-052).
- Input and output token counts and cost estimate.
- Verification checklist results.
- Escalation reason if refused.
- Timestamps for each step.

Audit records are immutable once written. Operators can export the full audit
trail from the BPS dashboard in JSON format for submission to compliance or
audit functions.

Retention period must be configured to meet the organisation's regulatory
obligations (minimum seven years recommended for financial services).
