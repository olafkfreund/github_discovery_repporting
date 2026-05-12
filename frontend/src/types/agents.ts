// Types for the Agents Running feature (issue #28)
// Usage:
//   import type { AgentRun, AgentRunStatus, ... } from '../types/agents'

export type AgentRunStatus =
  | 'pending'
  | 'running'
  | 'opening_pr'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type AgentStepType =
  | 'llm_call'
  | 'tool_call'
  | 'tool_result'
  | 'observation'
  | 'final'

export type RemediationActionStatus =
  | 'planned'
  | 'in_progress'
  | 'opened'
  | 'merged'
  | 'closed'
  | 'failed'

export interface AgentRun {
  id: string
  scan_id: string
  llm_connection_id: string
  provider: string
  model: string
  status: AgentRunStatus
  started_at: string | null
  finished_at: string | null
  total_input_tokens: number
  total_output_tokens: number
  total_cost_usd: number
  error: string | null
  runtime_mode: 'backend' | 'ci'
  created_at: string
  updated_at: string
}

export interface AgentStep {
  id: string
  agent_run_id: string
  step_index: number
  step_type: AgentStepType
  prompt_hash: string | null
  tool_name: string | null
  tool_args_redacted: Record<string, unknown> | null
  tool_result_redacted: string | null
  input_tokens: number
  output_tokens: number
  latency_ms: number
  status: string
  created_at: string
}

export interface RemediationAction {
  id: string
  agent_run_id: string
  finding_id: string
  check_id: string
  pr_url: string | null
  branch: string | null
  status: RemediationActionStatus
  opened_at: string | null
  merged_at: string | null
}

export interface AgentRunDetailed extends AgentRun {
  steps: AgentStep[]
  actions: RemediationAction[]
}

export interface RemediationPolicy {
  id: string
  customer_id: string
  enabled: boolean
  auto_dispatch: boolean
  kill_switch_enabled: boolean
  allowed_check_ids: string[]
  blocked_check_ids: string[]
  max_prs_per_scan: number
  max_cost_usd_per_month: number
  allowed_path_globs: string[]
  denied_path_globs: string[]
  runtime_mode: 'backend' | 'ci'
  oversight_mode: 'strict' | 'standard'
  llm_input_scope: 'hunk' | 'file' | 'repo-context'
  created_at: string
  updated_at: string
}

export interface RemediationPolicyUpsertPayload {
  enabled?: boolean
  auto_dispatch?: boolean
  kill_switch_enabled?: boolean
  allowed_check_ids?: string[]
  blocked_check_ids?: string[]
  max_prs_per_scan?: number
  max_cost_usd_per_month?: number
  allowed_path_globs?: string[]
  denied_path_globs?: string[]
  runtime_mode?: 'backend' | 'ci'
  oversight_mode?: 'strict' | 'standard'
  llm_input_scope?: 'hunk' | 'file' | 'repo-context'
}

export interface AgentRunCostEstimate {
  min_usd: number
  max_usd: number
  expected_tokens: number
}

export interface AgentRunTriggerPayload {
  llm_connection_id: string
  runtime_mode: 'backend' | 'ci'
  check_ids?: string[]
}
