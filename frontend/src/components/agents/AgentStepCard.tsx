// AgentStepCard — renders a single step in the agent run timeline (issue #30)
//
// Usage:
//   <AgentStepCard step={step} />

import { useState } from 'react'
import type { AgentStep } from '../../types/agents'
import { AgentStepTypeBadge } from '../ui/AgentStatusBadge'

interface Props {
  step: AgentStep
}

function primaryText(step: AgentStep): string {
  switch (step.step_type) {
    case 'llm_call':
      return `LLM call · ${step.input_tokens} in / ${step.output_tokens} out tokens`
    case 'tool_call': {
      const argsSnippet = step.tool_args_redacted
        ? JSON.stringify(step.tool_args_redacted).slice(0, 80)
        : ''
      return `${step.tool_name ?? 'unknown'} ${argsSnippet}${argsSnippet.length >= 80 ? '…' : ''}`
    }
    case 'tool_result': {
      if (!step.tool_result_redacted) return '(no output)'
      const snippet = step.tool_result_redacted.slice(0, 80)
      return snippet + (step.tool_result_redacted.length > 80 ? '…' : '')
    }
    case 'final':
      return `Final · ${step.status}`
    case 'observation':
      return step.tool_result_redacted?.slice(0, 80) ?? '(observation)'
    default:
      return ''
  }
}

export function AgentStepCard({ step }: Props) {
  const [expanded, setExpanded] = useState(false)

  const timestamp = new Date(step.created_at).toLocaleTimeString()
  const hasDetails =
    step.tool_args_redacted !== null || step.tool_result_redacted !== null

  return (
    <li className="flex gap-3 py-2 border-b border-gray-100 last:border-0">
      {/* Timestamp */}
      <span className="shrink-0 w-20 text-xs text-gray-400 tabular-nums pt-0.5">
        {timestamp}
      </span>

      <div className="flex-1 min-w-0">
        {/* Badge + primary text */}
        <div className="flex items-start gap-2 flex-wrap">
          <AgentStepTypeBadge type={step.step_type} />
          <span className="text-sm text-gray-700 break-all">{primaryText(step)}</span>
        </div>

        {/* Tokens / latency / status row */}
        <div className="mt-0.5 flex items-center gap-2 text-xs text-gray-400">
          {(step.input_tokens > 0 || step.output_tokens > 0) && (
            <span>{step.input_tokens}↑ {step.output_tokens}↓ tokens</span>
          )}
          {step.latency_ms > 0 && <span>{step.latency_ms}ms</span>}
          {step.status && <span className="capitalize">{step.status}</span>}
        </div>

        {/* Expander */}
        {hasDetails && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-1 text-xs text-brand-600 hover:text-brand-800 focus:outline-none focus:underline"
            aria-expanded={expanded}
          >
            {expanded ? '▾ hide details' : '▸ details'}
          </button>
        )}

        {expanded && (
          <div className="mt-2 space-y-2">
            {step.tool_args_redacted !== null && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Args</p>
                <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">
                  {JSON.stringify(step.tool_args_redacted, null, 2)}
                </pre>
              </div>
            )}
            {step.tool_result_redacted !== null && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Result</p>
                <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">
                  {step.tool_result_redacted}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  )
}
