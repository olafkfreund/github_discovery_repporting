// Usage:
//   import ConnectionOverrideRow from './ConnectionOverrideRow'
//   <ConnectionOverrideRow connection={conn} onChange={handleOverrideChange} />
//
// onChange receives the connection id and the new override value (or null to clear).
// The component manages its own debounced PUT and displays Saving / Saved / Failed.

import { useState, useEffect, useRef, useId } from 'react'
import type { Connection } from '../../types'
import { ConfirmDialog } from '../ui/ConfirmDialog'

const PLATFORM_BADGE: Record<Connection['platform'], string> = {
  github: 'bg-gray-100 text-gray-800',
  gitlab: 'bg-orange-100 text-orange-800',
  azure_devops: 'bg-blue-100 text-blue-800',
}

const PLATFORM_LABEL: Record<Connection['platform'], string> = {
  github: 'GitHub',
  gitlab: 'GitLab',
  azure_devops: 'Azure DevOps',
}

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

interface Props {
  connection: Connection
  onChange: (id: string, override: string | null) => Promise<void>
}

export default function ConnectionOverrideRow({ connection, onChange }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [draft, setDraft] = useState(connection.agent_instructions_override ?? '')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [confirmClearOpen, setConfirmClearOpen] = useState(false)

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const textareaId = useId()
  const panelId = useId()

  // Sync when parent passes a refreshed connection
  useEffect(() => {
    setDraft(connection.agent_instructions_override ?? '')
  }, [connection.agent_instructions_override])

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
      if (clearTimerRef.current) clearTimeout(clearTimerRef.current)
    }
  }, [])

  const hasActiveOverride = (connection.agent_instructions_override ?? '').length > 0

  function handleChange(value: string) {
    setDraft(value)
    setStatus('idle')
    setErrorMsg(null)

    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      void performSave(value)
    }, 1000)
  }

  async function performSave(value: string) {
    const override = value.trim().length === 0 ? null : value
    setStatus('saving')
    setErrorMsg(null)
    try {
      await onChange(connection.id, override)
      setStatus('saved')
      if (clearTimerRef.current) clearTimeout(clearTimerRef.current)
      clearTimerRef.current = setTimeout(() => setStatus('idle'), 2000)
    } catch (err) {
      setStatus('error')
      setErrorMsg(err instanceof Error ? err.message : 'Save failed')
    }
  }

  async function handleClearOverride() {
    setConfirmClearOpen(false)
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    setDraft('')
    await performSave('')
  }

  const overrideActive = draft.trim().length > 0 || hasActiveOverride

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Header / expander */}
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-brand-500"
      >
        {/* Expand icon */}
        <svg
          className={`h-4 w-4 text-gray-400 flex-shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>

        {/* Platform badge */}
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium flex-shrink-0 ${PLATFORM_BADGE[connection.platform]}`}
        >
          {PLATFORM_LABEL[connection.platform]}
        </span>

        {/* Connection name */}
        <span className="text-sm font-medium text-gray-900">{connection.display_name}</span>

        {/* Org/group label */}
        <span className="text-xs text-gray-500 truncate">
          (org/group: {connection.org_or_group})
        </span>

        {/* Override status badge */}
        <span className="ml-auto flex-shrink-0 text-xs">
          {overrideActive ? (
            <span className="text-amber-700 font-medium">Override active</span>
          ) : (
            <span className="text-gray-400">Uses customer default</span>
          )}
        </span>
      </button>

      {/* Expandable panel */}
      {expanded && (
        <div id={panelId} className="px-4 pb-4 bg-gray-50 border-t border-gray-200">
          <div className="pt-3">
            <div className="flex items-center justify-between mb-1">
              <label
                htmlFor={textareaId}
                className="block text-xs font-medium text-gray-700"
              >
                {overrideActive
                  ? 'Override active — supersedes customer default'
                  : 'Uses customer default. Type here to override:'}
              </label>

              {/* Save status indicator */}
              <span aria-live="polite" className="text-xs ml-2">
                {status === 'saving' && (
                  <span className="text-gray-500">Saving…</span>
                )}
                {status === 'saved' && (
                  <span className="text-emerald-700">Saved</span>
                )}
                {status === 'error' && (
                  <span className="text-red-700">Failed: {errorMsg}</span>
                )}
              </span>
            </div>

            <textarea
              id={textareaId}
              value={draft}
              onChange={(e) => handleChange(e.target.value)}
              rows={10}
              spellCheck={false}
              className="font-mono text-sm border border-gray-300 rounded-md p-3 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full resize-y"
              placeholder="Leave empty to use the customer-level instructions…"
            />

            {/* Clear override button */}
            {overrideActive && (
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  onClick={() => setConfirmClearOpen(true)}
                  className="text-sm text-red-600 font-medium hover:text-red-700 focus:outline-none focus:underline"
                >
                  Clear override
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Clear confirmation dialog */}
      <ConfirmDialog
        open={confirmClearOpen}
        title="Clear Override"
        message={`Remove the per-connection override for "${connection.display_name}"? The customer-level instructions will be used instead.`}
        confirmLabel="Clear override"
        variant="danger"
        onConfirm={() => { void handleClearOverride() }}
        onCancel={() => setConfirmClearOpen(false)}
      />
    </div>
  )
}
