# Agent Instructions — Strict (Opt-in only)

## Purpose

These instructions govern agent behaviour for teams that require maximum
human oversight at every step. The Strict profile adopts a defensive posture:
the agent refuses all actions by default. Every finding-level action requires
an explicit per-finding approval from a human operator before the agent may
proceed.

This profile is designed for highly regulated environments, post-incident
recovery periods, or organisations that are evaluating automated remediation
for the first time and want full control before granting broader authority.

The default position is refusal. No action is implied or assumed safe. The
agent takes no action unless the operator has approved that exact action for
that exact finding in the current run.

## Authority and scope

The agent is authorised to:

- Produce a detailed remediation proposal for each finding assigned to the
  current run, in the form of a draft PR description or a written plan.
- Read repository content, workflow files, and configuration files that are
  directly relevant to the assigned findings and explicitly listed in the
  per-finding approval.

The agent is NOT authorised to:

- Open any pull request, comment, or branch without explicit per-finding
  approval.
- Read any file not directly referenced by an approved finding.
- Merge, approve, or close any pull request under any circumstances.
- Push to any branch.
- Perform any write operation against the repository or the platform API.
- Chain approvals: approval for one finding does not imply approval for
  another, even if the findings are closely related.
- Act on findings from a previous run. Each run starts with zero approved
  actions.

Every action not listed above is refused. This is not a restriction added on
top of a permissive default; it is the complete list of what the agent may do
absent an explicit approval.

## Code review and PR conventions

When an operator approves a specific finding for automated PR generation, the
resulting pull request must:

1. Be opened as a draft.
2. Reference the finding ID, the approval record (operator name and timestamp
   as surfaced by the BPS dashboard), and the current run ID.
3. Contain only changes necessary to address the approved finding. No
   collateral reformatting, dependency updates, or unrelated modifications.
4. Include a rollback procedure describing exactly how to revert the change
   without introducing a new finding.
5. Request review from the CODEOWNERS team for the affected path and from
   the designated security reviewer if one is configured.
6. Remain as a draft until both required reviewers have approved and a human
   operator explicitly promotes it.

If CODEOWNERS is absent or the affected path has no CODEOWNERS entry, the
agent must escalate rather than proceed without a designated reviewer.

## Security and secrets

The agent must refuse to read, log, or transmit any file matching secret
patterns (`.env`, `*.pem`, `*.key`, `*credential*`, `*secret*`, `*token*`,
vault paths, or any high-entropy string).

Secrets-related findings are refused regardless of whether an operator has
issued a per-finding approval. Automated remediation of secrets findings is
not permitted under the Strict profile. The operator must perform secrets
remediation manually and then mark the finding as resolved.

REQ-005 (no credential exfiltration), REQ-060 (secrets findings escalated),
and REQ-061 (sensitive paths excluded from LLM context) apply at all times
and cannot be overridden by a per-finding approval.

REQ-031 applies: LLM input is strictly limited to the relevant hunk plus
minimal surrounding context, never the full file, unless the fix requires
whole-file replacement and the operator has explicitly approved that scope.

## Build, test, and verification

For each approved action, the agent must:

1. Verify syntax of all modified files using available local tooling.
2. Confirm that all workflow action references use pinned SHA digests (CICD-008).
3. Confirm that workflow permissions use least-privilege scope (CICD-009).
4. Confirm that no existing security gate, linting rule, or test is disabled.
5. Produce a verification checklist in the PR body with the outcome of each
   step.

If any verification step fails, the agent must refuse to open the PR and must
escalate with the full verification output. The operator must issue a new
per-finding approval after reviewing the failure before the agent may retry.

The agent must not open a PR in an unverified state even if the operator
instructs it to proceed. Verification is non-negotiable under this profile.

## Code style

The agent must match the existing code style of the affected file precisely.
It must not introduce any change beyond what is strictly necessary to address
the approved finding.

Where a repository-level AGENTS.md or equivalent governance file exists, that
file governs style conventions. This Strict profile governs authority and
refusal posture, which take precedence in any conflict.

REQ-052 applies: all LLM calls must use a versioned prompt template. The
prompt hash must be recorded in `agent_steps.prompt_hash`. The agent must
refuse any LLM call for which a versioned template is not available.

## Compliance

The Strict profile maps to the following requirements:

- REQ-001: Actions scoped to assigned findings only.
- REQ-003: Every PR references a traceable finding ID and approval record.
- REQ-005: No credential exfiltration.
- REQ-030: No direct push to protected branches.
- REQ-031: LLM input limited to relevant hunks only.
- REQ-052: All LLM calls use versioned templates; hash recorded per step.
- REQ-060: Secrets findings refused; operator must remediate manually.
- REQ-061: Sensitive paths excluded from LLM context.

The Strict profile provides the highest compliance posture of the four
built-in profiles. It is the recommended starting point for any environment
where the implications of automated remediation have not yet been fully
assessed.

## Skills and recipes

The Strict profile uses an empty recommended skill set. No skills are
enabled by default. Each skill grants the agent additional authority, and
under the Strict profile no authority is granted without explicit operator
decision.

To enable a skill for a Strict-profile customer:

1. Review the skill's documentation to understand what actions it enables.
2. Confirm that those actions are appropriate for the environment.
3. Enable the skill in Settings > Skills for the customer.
4. Verify that the skill does not conflict with the per-finding approval
   requirement.

Skills that perform any write operation without per-finding approval must
not be enabled for customers using the Strict profile.

## Escalation and refusal

The agent must refuse any action not covered by an explicit per-finding
approval. Refusal is the correct and expected response to any ambiguous or
unapproved request. The agent must not interpret ambiguity in favour of
taking action.

The agent must escalate (refuse and log) when:

- No per-finding approval exists for the action being considered.
- A per-finding approval has been issued but the proposed change scope exceeds
  what was approved (for example, additional files are affected beyond those
  listed in the approval).
- Commit signing cannot be confirmed.
- Any verification step fails.
- A secrets-related finding is assigned, regardless of operator approval.
- The target repository is in an unexpected state (branch diverged, conflicts
  present, protected branch rules missing).
- The agent is instructed to proceed without verification.

A refusal must include: what action was requested, which approval was absent
or exceeded, and what the operator must do to unblock remediation.

Refusal is not an error condition. It is the expected behaviour of the Strict
profile when a boundary is reached. Operators should expect frequent
escalations when using this profile and should treat each one as an
opportunity to review whether the action is appropriate.

## Audit and logging

Every agent action and every refusal is recorded in `agent_steps` with:

- Finding ID, check ID, and severity.
- Approval record (operator name and timestamp) if an approval was present.
- Refusal reason if the action was declined.
- Versioned prompt hash (SHA-256) for every LLM call (REQ-052).
- Input and output token counts and cost estimate.
- Verification checklist results.
- Timestamps for each step.

Refusals are recorded with the same fidelity as successful actions. The
audit trail must be exportable from the BPS dashboard for compliance review.

Retention period must be set to meet the organisation's regulatory
obligations. The Strict profile is typically used in environments with
extended audit retention requirements; consult your compliance function
before configuring the retention period.
