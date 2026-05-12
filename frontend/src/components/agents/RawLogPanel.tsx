// RawLogPanel — collapsible raw log of all agent steps (issue #30)
//
// Usage:
//   <RawLogPanel steps={steps} />

import { useState } from 'react'
import type { AgentStep } from '../../types/agents'

interface Props {
  steps: AgentStep[]
}

function stepToLogLine(step: AgentStep): string {
  const ts = step.created_at
  const type = `[${step.step_type}]`

  switch (step.step_type) {
    case 'llm_call':
      return `${ts} ${type} input=${step.input_tokens} output=${step.output_tokens} latency=${step.latency_ms}ms`
    case 'tool_call': {
      const args = step.tool_args_redacted
        ? JSON.stringify(step.tool_args_redacted)
        : '{}'
      return `${ts} ${type} ${step.tool_name ?? 'unknown'} ${args}`
    }
    case 'tool_result': {
      const result = step.tool_result_redacted ?? ''
      return `${ts} ${type} ${step.status} len=${result.length}`
    }
    case 'final':
      return `${ts} ${type} status=${step.status}`
    case 'observation':
      return `${ts} ${type} ${step.tool_result_redacted ?? ''}`
    default:
      return `${ts} ${type}`
  }
}

export function RawLogPanel({ steps }: Props) {
  const [copied, setCopied] = useState(false)

  const sorted = steps.slice().sort((a, b) => a.step_index - b.step_index)
  const logText = sorted.map(stepToLogLine).join('\n')

  const handleCopy = () => {
    void navigator.clipboard.writeText(logText).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <details className="mt-8 border border-gray-200 rounded-lg">
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 rounded-lg select-none">
        Raw log ({steps.length} steps)
      </summary>

      <div className="px-4 pb-4 pt-2">
        <div className="flex justify-end mb-2">
          <button
            type="button"
            onClick={handleCopy}
            className="text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded px-2 py-1
                       focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1"
            aria-label="Copy raw log to clipboard"
          >
            {copied ? 'Copied!' : 'Copy to clipboard'}
          </button>
        </div>
        <pre className="font-mono text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-x-auto whitespace-pre">
          {logText || '(no steps yet)'}
        </pre>
      </div>
    </details>
  )
}
