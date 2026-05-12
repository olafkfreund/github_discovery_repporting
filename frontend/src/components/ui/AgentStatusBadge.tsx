// Usage:
//   import { AgentRunStatusBadge, AgentStepTypeBadge } from '../components/ui/AgentStatusBadge'
//
//   <AgentRunStatusBadge status="running" />
//   <AgentStepTypeBadge type="tool_call" />

import type { AgentRunStatus, AgentStepType } from '../../types/agents'

export const AGENT_RUN_STATUS_CLASSES: Record<AgentRunStatus, string> = {
  pending:    'bg-gray-100 text-gray-700',
  running:    'bg-blue-100 text-blue-800',
  opening_pr: 'bg-purple-100 text-purple-800',
  completed:  'bg-green-100 text-green-800',
  failed:     'bg-red-100 text-red-800',
  cancelled:  'bg-yellow-100 text-yellow-900',
}

const AGENT_RUN_STATUS_LABELS: Record<AgentRunStatus, string> = {
  pending:    'pending',
  running:    'running',
  opening_pr: 'opening PR',
  completed:  'completed',
  failed:     'failed',
  cancelled:  'cancelled',
}

export function AgentRunStatusBadge({ status }: { status: AgentRunStatus }) {
  const showPulse = status === 'running' || status === 'opening_pr'
  const dotColor = status === 'opening_pr' ? 'bg-purple-600' : 'bg-blue-600'
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${AGENT_RUN_STATUS_CLASSES[status]}`}
    >
      {showPulse && (
        <span
          className={`w-1.5 h-1.5 rounded-full ${dotColor} animate-pulse mr-1.5`}
          aria-hidden="true"
        />
      )}
      {AGENT_RUN_STATUS_LABELS[status]}
    </span>
  )
}

export const AGENT_STEP_TYPE_CLASSES: Record<AgentStepType, string> = {
  llm_call:    'bg-brand-100 text-brand-900',
  tool_call:   'bg-blue-100 text-blue-800',
  tool_result: 'bg-emerald-100 text-emerald-900',
  observation: 'bg-gray-100 text-gray-700',
  final:       'bg-accent-200 text-brand-900',
}

const AGENT_STEP_TYPE_LABELS: Record<AgentStepType, string> = {
  llm_call:    'llm call',
  tool_call:   'tool call',
  tool_result: 'tool result',
  observation: 'observation',
  final:       'final',
}

export function AgentStepTypeBadge({ type }: { type: AgentStepType }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${AGENT_STEP_TYPE_CLASSES[type]}`}
    >
      {AGENT_STEP_TYPE_LABELS[type]}
    </span>
  )
}
